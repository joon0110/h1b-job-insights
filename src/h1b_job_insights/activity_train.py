import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from xgboost import XGBClassifier

from h1b_job_insights import activity_features
from h1b_job_insights.activity_data import quarter_number, sha256
from h1b_job_insights.activity_features import FEATURES
from h1b_job_insights.company_activity import quarter_label

SEED = 42
TREND_CONSTRAINTS = {
    "recent_change": 1,
    "recent_slope": 1,
    "annual_change": 1,
    "annual_growth": 1,
    "active_last4": 1,
    "inactive_quarters": -1,
}
CANDIDATES = {
    "random_forest": [
        {"n_estimators": 160, "max_depth": 8, "min_samples_leaf": 50},
        {"n_estimators": 160, "max_depth": 12, "min_samples_leaf": 30},
        {"n_estimators": 160, "max_depth": 16, "min_samples_leaf": 50},
    ],
    "xgboost": [
        {"learning_rate": rate, "max_depth": depth, "n_estimators": 700}
        for depth in (3, 5)
        for rate in (0.05, 0.1)
    ],
}


def make_model(name: str, parameters: dict, jobs: int, stopping: bool = False):
    if name == "random_forest":
        return RandomForestClassifier(
            **parameters, max_features=0.7, n_jobs=jobs, random_state=SEED
        )
    if name == "xgboost":
        return XGBClassifier(
            **parameters,
            objective="binary:logistic",
            eval_metric="logloss",
            tree_method="hist",
            min_child_weight=20,
            reg_lambda=10,
            subsample=0.8,
            colsample_bytree=0.8,
            early_stopping_rounds=40 if stopping else None,
            n_jobs=jobs,
            random_state=SEED,
        )
    raise ValueError(f"Unknown model: {name}")


def split_at(frame: pd.DataFrame, origin: int) -> tuple[pd.Series, pd.Series]:
    training = frame.target_active.notna() & frame.target_quarter.le(origin)
    evaluation = frame.origin.eq(origin) & frame.target_active.notna()
    if not training.any() or not evaluation.any():
        raise ValueError(f"Missing training or evaluation rows for {quarter_label(origin)}")
    if not frame.loc[training, "origin"].lt(origin).all():
        raise ValueError("Training examples overlap the prediction origin")
    return training, evaluation


def log_odds(probability) -> np.ndarray:
    p = np.clip(np.asarray(probability, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p)).reshape(-1, 1)


def calibrate(calibrator, probability) -> np.ndarray:
    return calibrator.predict_proba(log_odds(probability))[:, 1]


def fit_at(frame, name, parameters, origin, jobs):
    training, evaluation = split_at(frame, origin)
    print(f"Fit {name} through {quarter_label(origin)}: {training.sum():,} rows", flush=True)
    model = make_model(name, parameters, jobs)
    model.fit(frame.loc[training, FEATURES], frame.loc[training, "target_active"].astype(int))
    return model, frame.loc[evaluation]


def run(
    data_dir: Path,
    output_dir: Path,
    jobs: int = 4,
    constrain_trends: bool = False,
    reuse_random_forest: Path | None = None,
) -> dict:
    manifest = json.loads((data_dir / "manifest.json").read_text())
    if (
        manifest["features"] != FEATURES
        or manifest["feature_code_sha256"] != sha256(Path(activity_features.__file__))
        or manifest["examples_sha256"] != sha256(data_dir / "examples.parquet")
        or manifest["panel_sha256"] != sha256(data_dir / "company_quarters.parquet")
    ):
        raise ValueError("Activity inputs changed; rebuild the examples")
    if manifest["last_quarter"] != "FY2026_Q2":
        raise ValueError("This training setup expects history ending at FY2026 Q2")
    frame = pd.read_parquet(data_dir / "examples.parquet")
    if not np.isfinite(frame[FEATURES].to_numpy()).all():
        raise ValueError("Nonfinite features")
    if not frame.target_active.dropna().isin([0, 1]).all():
        raise ValueError("Labels must be 0 or 1")
    if not (frame.target_quarter == frame.origin + frame.horizon).all():
        raise ValueError("Prediction horizons do not match their targets")
    candidates_by_model = {
        name: [dict(settings) for settings in candidates] for name, candidates in CANDIDATES.items()
    }
    if constrain_trends:
        for settings in candidates_by_model["xgboost"]:
            settings["monotone_constraints"] = TREND_CONSTRAINTS.copy()
    reused = None
    if reuse_random_forest is not None:
        if output_dir.resolve() == reuse_random_forest.resolve():
            raise ValueError("Use a separate output directory when reusing Random Forest")
        reused = joblib.load(reuse_random_forest / "classifiers.joblib")
        if (
            reused["selection"]["input_manifest"] != manifest
            or reused["features"] != FEATURES
            or reused["trained_through"] != quarter_number("FY2026_Q2")
            or reused["selection"]["selection_origin"] != "FY2025_Q2"
            or reused["selection"]["calibration_origin"] != "FY2024_Q4"
        ):
            raise ValueError("Saved Random Forest uses different data or time splits")
    output_dir.mkdir(parents=True, exist_ok=True)
    tuning = []
    parameters = {}
    for name, candidates in candidates_by_model.items():
        if reused is not None and name == "random_forest":
            parameters[name] = reused["selection"]["parameters"][name]
            candidates_by_model[name] = reused["selection"]["candidates"][name]
            print("Reuse Random Forest settings and fitted model", flush=True)
            continue
        for candidate, settings in enumerate(candidates):
            for label in ("FY2023_Q4", "FY2024_Q2"):
                origin = quarter_number(label)
                training, evaluation = split_at(frame, origin)
                print(f"Tune {name} {candidate + 1}/{len(candidates)}, origin {label}", flush=True)
                model = make_model(name, settings, jobs, stopping=name == "xgboost")
                options = {}
                if name == "xgboost":
                    options = {
                        "eval_set": [
                            (
                                frame.loc[evaluation, FEATURES],
                                frame.loc[evaluation, "target_active"],
                            )
                        ],
                        "verbose": False,
                    }
                model.fit(
                    frame.loc[training, FEATURES], frame.loc[training, "target_active"], **options
                )
                p = model.predict_proba(frame.loc[evaluation, FEATURES])[:, 1]
                tuning.append(
                    {
                        "model": name,
                        "candidate": candidate,
                        "trees": int(model.best_iteration + 1)
                        if name == "xgboost"
                        else settings["n_estimators"],
                        "log_loss": float(
                            log_loss(
                                frame.loc[evaluation, "target_active"],
                                np.clip(p, 1e-7, 1 - 1e-7),
                                labels=[0, 1],
                            )
                        ),
                    }
                )
            del model
        ranked = pd.DataFrame(tuning).query("model == @name").groupby("candidate").log_loss.mean()
        best = int(ranked.idxmin())
        parameters[name] = candidates[best].copy()
        if name == "xgboost":
            iterations = [
                r["trees"] for r in tuning if r["model"] == name and r["candidate"] == best
            ]
            parameters[name]["n_estimators"] = int(np.median(iterations))
        print(f"Selected {name}: {parameters[name]}", flush=True)

    selection_origin = quarter_number("FY2025_Q2")
    calibrators = {}
    use_calibration = {}
    for name in CANDIDATES:
        if reused is not None and name == "random_forest":
            calibrators[name] = reused["calibrators"][name]
            use_calibration[name] = reused["selection"]["use_calibration"][name]
            continue
        model, calibration_rows = fit_at(
            frame, name, parameters[name], quarter_number("FY2024_Q4"), jobs
        )
        p = model.predict_proba(calibration_rows[FEATURES])[:, 1]
        calibrators[name] = LogisticRegression(C=1.0, solver="lbfgs").fit(
            log_odds(p), calibration_rows.target_active.astype(int)
        )
        model, selection_rows = fit_at(frame, name, parameters[name], selection_origin, jobs)
        raw = model.predict_proba(selection_rows[FEATURES])[:, 1]
        adjusted = calibrate(calibrators[name], raw)
        raw_loss = log_loss(
            selection_rows.target_active, np.clip(raw, 1e-7, 1 - 1e-7), labels=[0, 1]
        )
        adjusted_loss = log_loss(
            selection_rows.target_active, np.clip(adjusted, 1e-7, 1 - 1e-7), labels=[0, 1]
        )
        calibration_allowed = (
            not (constrain_trends and name == "xgboost") or calibrators[name].coef_[0, 0] > 0
        )
        use_calibration[name] = bool(calibration_allowed and adjusted_loss < raw_loss)
        del model
    selection = {
        "selection_metric": "log_loss",
        "parameters": parameters,
        "use_calibration": use_calibration,
        "candidates": candidates_by_model,
        "trend_constraints": TREND_CONSTRAINTS if constrain_trends else {},
        "tuning_origins": ["FY2023_Q4", "FY2024_Q2"],
        "calibration_origin": "FY2024_Q4",
        "selection_origin": "FY2025_Q2",
        "input_manifest": manifest,
    }
    final_end = quarter_number(manifest["last_quarter"])
    training = frame.target_active.notna() & frame.target_quarter.le(final_end)
    final_models = {}
    for name in CANDIDATES:
        if reused is not None and name == "random_forest":
            final_models[name] = reused["models"][name]
            continue
        print(f"Final fit {name} through FY2026 Q2: {training.sum():,} rows", flush=True)
        model = make_model(name, parameters[name], jobs)
        model.fit(frame.loc[training, FEATURES], frame.loc[training, "target_active"].astype(int))
        final_models[name] = model
    joblib.dump(
        {
            "models": final_models,
            "calibrators": calibrators,
            "selection": selection,
            "features": FEATURES,
            "training_rows": int(training.sum()),
            "trained_through": final_end,
            "panel_sha256": manifest["panel_sha256"],
            "feature_code_sha256": manifest["feature_code_sha256"],
        },
        output_dir / "classifiers.joblib",
        compress=3,
    )
    print(f"Saved models: {output_dir / 'classifiers.joblib'}", flush=True)
    return selection


def main() -> None:
    parser = argparse.ArgumentParser(description="Train H-1B LCA filing probability models")
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed/activity"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/activity"))
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--constrain-trends", action="store_true")
    parser.add_argument("--reuse-random-forest", type=Path)
    args = parser.parse_args()
    run(args.data_dir, args.output_dir, args.jobs, args.constrain_trends, args.reuse_random_forest)


if __name__ == "__main__":
    main()
