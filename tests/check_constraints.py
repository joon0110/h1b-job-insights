import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from h1b_job_insights.activity_features import FEATURES
from h1b_job_insights.activity_predict import load_bundle
from h1b_job_insights.activity_train import SEED, TREND_CONSTRAINTS, calibrate


def check_monotonicity(model, rows: pd.DataFrame, calibrator=None) -> pd.DataFrame:
    sample = rows[FEATURES].sample(min(512, len(rows)), random_state=SEED).copy()
    grids = {
        "recent_change": [-1000, -100, -10, -1, 0, 1, 10, 100, 1000],
        "recent_slope": [-500, -50, -5, -1, 0, 1, 5, 50, 500],
        "annual_change": [-4000, -400, -40, -4, 0, 4, 40, 400, 4000],
        "annual_growth": [-1, -0.5, -0.1, 0, 0.1, 0.5, 1, 2, 5],
        "active_last4": [0, 1, 2, 3, 4],
        "inactive_quarters": [0, 1, 2, 3, 4, 8, 12, 16],
    }
    checks = []
    for feature, direction in TREND_CONSTRAINTS.items():
        probabilities = []
        for value in grids[feature]:
            changed = sample.copy()
            changed[feature] = np.float32(value)
            p = model.predict_proba(changed)[:, 1]
            probabilities.append(calibrate(calibrator, p) if calibrator is not None else p)
        differences = direction * np.diff(np.column_stack(probabilities), axis=1)
        violations = int((differences < -1e-7).sum())
        if violations:
            raise ValueError(f"Monotonicity violated for {feature}: {violations} comparisons")
        checks.append(
            {
                "feature": feature,
                "direction": direction,
                "rows": len(sample),
                "comparisons": differences.size,
                "violations": violations,
                "rows_with_change": int((differences > 1e-7).any(axis=1).sum()),
            }
        )
    return pd.DataFrame(checks)


def main():
    parser = argparse.ArgumentParser(description="Check saved XGBoost trend constraints")
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed/activity"))
    parser.add_argument("--model-dir", type=Path, default=Path("artifacts/activity"))
    args = parser.parse_args()
    bundle = load_bundle(args.data_dir, args.model_dir)
    if bundle["selection"].get("trend_constraints") != TREND_CONSTRAINTS:
        raise ValueError("Select an XGBoost model trained with trend constraints")
    rows = pd.read_parquet(
        args.data_dir / "examples.parquet",
        filters=[("origin", "=", bundle["trained_through"]), ("horizon", "=", 1)],
    )
    if rows.empty:
        raise ValueError("No rows at the model's history cutoff")
    calibrator = (
        bundle["calibrators"]["xgboost"]
        if bundle["selection"]["use_calibration"]["xgboost"]
        else None
    )
    report = check_monotonicity(bundle["models"]["xgboost"], rows, calibrator)
    print(report.to_string(index=False))


if __name__ == "__main__":
    main()
