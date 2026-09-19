import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score

from h1b_job_insights import activity_train as train
from h1b_job_insights.activity_data import quarter_number, sha256
from h1b_job_insights.activity_features import FEATURES
from h1b_job_insights.activity_predict import load_bundle
from h1b_job_insights.company_activity import quarter_label


def scores(actual, probability) -> dict:
    y = np.asarray(actual)
    p = np.asarray(probability, dtype=float)
    if (
        y.ndim != 1
        or p.shape != y.shape
        or not len(y)
        or not np.isin(y, [0, 1]).all()
        or not np.isfinite(p).all()
        or ((p < 0) | (p > 1)).any()
    ):
        raise ValueError("Invalid labels or probabilities")
    both = len(np.unique(y)) == 2
    return {
        "rows": len(y),
        "actual_rate": float(y.mean()),
        "mean_probability": float(p.mean()),
        "log_loss": float(log_loss(y, np.clip(p, 1e-7, 1 - 1e-7), labels=[0, 1])),
        "brier": float(brier_score_loss(y, p)),
        "average_precision": float(average_precision_score(y, p)) if both else None,
        "roc_auc": float(roc_auc_score(y, p)) if both else None,
    }


def reliability(frame: pd.DataFrame, method: str) -> pd.DataFrame:
    p = frame[method]
    groups = [
        (f"{lo}–{lo + 10}%", p.ge(lo / 100) & p.lt((lo + 10) / 100)) for lo in range(0, 100, 10)
    ]
    groups[-1] = ("90–100%", p.ge(0.9) & p.le(1))
    groups.extend((f">={threshold}%", p.ge(threshold / 100)) for threshold in (95, 99))
    return pd.DataFrame(
        [
            {
                "probability_band": label,
                "rows": int(mask.sum()),
                "mean_probability": frame.loc[mask, method].mean(),
                "actual_rate": frame.loc[mask, "target_active"].mean(),
            }
            for label, mask in groups
            if mask.any()
        ]
    )


def evaluate(data_dir: Path, model_dir: Path, output_dir: Path, jobs: int = 4):
    if output_dir.resolve() in (data_dir.resolve(), model_dir.resolve()):
        raise ValueError("Use a separate directory for check results")
    bundle = load_bundle(data_dir, model_dir)
    frame = pd.read_parquet(data_dir / "examples.parquet")
    origin = quarter_number(bundle["selection"]["evaluation_origin"])
    if quarter_number(bundle["selection"]["selection_origin"]) + 2 > origin:
        raise ValueError("Model selection overlaps evaluation outcomes")
    training, evaluation = train.split_at(frame, origin)
    rows = frame.loc[evaluation]
    if set(rows.target_quarter) != {origin + 1, origin + 2}:
        raise ValueError("Both evaluation outcome quarters are required")
    if not np.isfinite(frame[FEATURES].to_numpy()).all():
        raise ValueError("Nonfinite model inputs")
    predictions = rows[
        [
            "EMPLOYER_ID",
            "EMPLOYER_NAME",
            "origin",
            "target_quarter",
            "horizon",
            "target_cases",
            "target_active",
        ]
    ].copy()
    for method in ("random_forest", "xgboost"):
        model, evaluation_rows = train.fit_at(
            frame, method, bundle["selection"]["parameters"][method], origin, jobs
        )
        p = model.predict_proba(evaluation_rows[FEATURES])[:, 1]
        if bundle["selection"]["use_calibration"][method]:
            p = train.calibrate(bundle["calibrators"][method], p)
        predictions[method] = p
        del model
    predictions["global_rate"] = frame.loc[training, "target_active"].mean()
    predictions["company_rate"] = (rows.history_active_rate * rows.history_quarters + 1) / (
        rows.history_quarters + 2
    )
    predictions["recent_rate"] = (rows.active_last4 + 1) / 6
    methods = ["random_forest", "xgboost", "global_rate", "company_rate", "recent_rate"]
    periods = [("all", predictions)] + [
        (quarter_label(q), group) for q, group in predictions.groupby("target_quarter")
    ]
    metrics = pd.DataFrame(
        [
            {"period": period, "model": method, **scores(group.target_active, group[method])}
            for period, group in periods
            for method in methods
        ]
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    predictions.to_parquet(output_dir / "predictions.parquet", index=False)
    metrics.to_csv(output_dir / "metrics.csv", index=False)
    for method in ("random_forest", "xgboost"):
        reliability(predictions, method).to_csv(
            output_dir / f"{method}_reliability.csv", index=False
        )
    (output_dir / "manifest.json").write_text(
        json.dumps(
            {
                "history_cutoff": quarter_label(origin),
                "outcomes": [quarter_label(origin + 1), quarter_label(origin + 2)],
                "model_sha256": sha256(model_dir / "classifiers.joblib"),
                "examples_sha256": sha256(data_dir / "examples.parquet"),
                "check_code_sha256": sha256(Path(__file__)),
                "basis": "revised disclosure files",
            },
            indent=2,
        )
        + "\n"
    )
    return predictions, metrics


def main():
    parser = argparse.ArgumentParser(description="Compare predictions with the last two quarters")
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed/activity"))
    parser.add_argument("--model-dir", type=Path, default=Path("artifacts/activity"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/checks/models"))
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    _, metrics = evaluate(args.data_dir, args.model_dir, args.output_dir, args.jobs)
    print(metrics.loc[metrics.period.eq("all")].to_string(index=False))
    print(f"Results: {args.output_dir}")


if __name__ == "__main__":
    main()
