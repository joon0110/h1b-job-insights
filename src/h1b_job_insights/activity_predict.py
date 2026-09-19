import argparse
import json
from pathlib import Path

import joblib
import pandas as pd

from h1b_job_insights import activity_features, normalize
from h1b_job_insights.activity_data import sha256
from h1b_job_insights.activity_train import calibrate
from h1b_job_insights.company_activity import quarter_label

MODEL_DIRS = {
    "xgboost": Path("artifacts/activity/trend_constraints"),
    "random_forest": Path("artifacts/activity"),
}


def load_bundle(data_dir: Path, model_dir: Path) -> dict:
    bundle = joblib.load(model_dir / "classifiers.joblib")
    manifest = json.loads((data_dir / "manifest.json").read_text())
    sources = json.loads((data_dir.parent / "source_manifest.json").read_text())
    versions = sorted(
        [[item["release"], item["sha256"]] for item in sources["files"] if item["kind"] == "main"]
    )
    if (
        bundle["features"] != activity_features.FEATURES
        or bundle["feature_code_sha256"] != sha256(Path(activity_features.__file__))
        or bundle["panel_sha256"] != sha256(data_dir / "company_quarters.parquet")
        or bundle["selection"]["input_manifest"]["examples_sha256"] != manifest["examples_sha256"]
        or manifest["examples_sha256"] != sha256(data_dir / "examples.parquet")
        or versions != manifest["version"]["sources"]
    ):
        raise ValueError("Data or feature code changed; rebuild inputs and retrain")
    return bundle


def predict(
    company: str, data_dir: Path, model_dir: Path, method: str = "xgboost"
) -> tuple[pd.DataFrame, pd.DataFrame]:
    name = normalize.employer_name(company)
    if not name:
        raise ValueError("Company name is empty")
    company_id = normalize.employer_id(name)
    history = pd.read_parquet(
        data_dir / "company_quarters.parquet", filters=[("EMPLOYER_ID", "=", company_id)]
    ).sort_values("FISCAL_QUARTER")
    if history.empty:
        raise ValueError(f"No H-1B LCA records found for {name}")
    bundle = load_bundle(data_dir, model_dir)
    rows = pd.read_parquet(
        data_dir / "examples.parquet",
        filters=[
            ("EMPLOYER_ID", "=", company_id),
            ("origin", "=", bundle["trained_through"]),
            ("horizon", "=", 1),
        ],
    )
    if rows.empty:
        raise ValueError(f"{name} has fewer than four quarters of history")
    result = rows[["EMPLOYER_NAME", "origin", "target_quarter"]].copy()
    model = bundle["models"][method]
    p = model.predict_proba(rows[bundle["features"]])[:, 1]
    if bundle["selection"]["use_calibration"][method]:
        p = calibrate(bundle["calibrators"][method], p)
    result["probability"] = p
    for column in ("origin", "target_quarter"):
        result[column] = result[column].map(quarter_label)
    return history, result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Show company history and next-quarter LCA probability"
    )
    parser.add_argument("--company", required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed/activity"))
    parser.add_argument("--model", choices=MODEL_DIRS, default="xgboost")
    parser.add_argument(
        "--model-dir", type=Path, help="Override the selected model's artifact directory"
    )
    args = parser.parse_args()
    model_dir = args.model_dir if args.model_dir is not None else MODEL_DIRS[args.model]
    history, result = predict(args.company, args.data_dir, model_dir, args.model)
    row = result.iloc[0]
    print(row.EMPLOYER_NAME)
    print("History by receipt date")
    print(history[["FISCAL_QUARTER", "LCA_CASES"]].to_string(index=False))
    print(f"\nHistory through {row.origin}; target {row.target_quarter}")
    print(f"Probability of at least one H-1B LCA record: {row.probability:.1%}")


if __name__ == "__main__":
    main()
