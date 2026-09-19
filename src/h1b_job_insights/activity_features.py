import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from h1b_job_insights.activity_data import prepare_panel, quarter_number, sha256

COMPANY_FEATURES = [
    "history_quarters",
    "history_mean",
    "history_active_rate",
    "history_max",
    "cases_recent1",
    "cases_recent2",
    "cases_recent3",
    "cases_recent4",
    "cases_last4",
    "active_last4",
    "recent_change",
    "recent_slope",
    "cases_previous4",
    "has_previous_year",
    "annual_change",
    "annual_growth",
    "inactive_quarters",
    "same_quarter_last_year",
    "same_quarter_mean",
    "same_quarter_active_rate",
    "same_quarter_observations",
]
MARKET_FEATURES = [
    "market_recent_cases",
    "market_last4_cases",
    "market_quarter_change",
    "market_annual_growth",
    "market_has_previous_year",
    "market_active_companies",
    "market_company_change",
    "market_season_mean",
    "company_market_share",
]
FEATURES = (
    COMPANY_FEATURES
    + MARKET_FEATURES
    + ["horizon", "target_q1", "target_q2", "target_q3", "target_q4"]
)


def history_arrays(frame: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    required = ["EMPLOYER_ID", "EMPLOYER_NAME", "FISCAL_QUARTER", "LCA_CASES"]
    if (
        frame.empty
        or frame[required].isna().any().any()
        or frame.duplicated(["EMPLOYER_ID", "FISCAL_QUARTER"]).any()
    ):
        raise ValueError("Missing or duplicate company quarters")
    if not frame.FISCAL_QUARTER.str.fullmatch(r"FY\d{4}_Q[1-4]").all():
        raise ValueError("Invalid fiscal quarter")
    values = frame.LCA_CASES.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < 0).any() or (values % 1 != 0).any():
        raise ValueError("Case counts must be nonnegative integers")
    if frame.groupby("EMPLOYER_ID").EMPLOYER_NAME.nunique().gt(1).any():
        raise ValueError("An employer ID has multiple names")
    names = frame[["EMPLOYER_ID", "EMPLOYER_NAME"]].drop_duplicates().sort_values("EMPLOYER_ID")
    wide = frame.pivot(index="EMPLOYER_ID", columns="FISCAL_QUARTER", values="LCA_CASES").reindex(
        names.EMPLOYER_ID
    )
    quarters = np.array([quarter_number(x) for x in wide.columns])
    if not np.all(np.diff(quarters) == 1):
        raise ValueError("Missing market quarter")
    counts = wide.to_numpy(dtype=float)
    known = ~np.isnan(counts)
    first = known.argmax(axis=1)
    expected = np.arange(len(quarters))[None, :] >= first[:, None]
    if not np.array_equal(known, expected) or (counts[np.arange(len(counts)), first] <= 0).any():
        raise ValueError("Company history must start with a case and continue without gaps")
    return names.reset_index(drop=True), counts, quarters


def build_examples(frame: pd.DataFrame, origins: list[int] | None = None) -> pd.DataFrame:
    names, counts, quarters = history_arrays(frame)
    observed = ~np.isnan(counts)
    clean = np.nan_to_num(counts)
    market = clean.sum(axis=0)
    market_companies = (clean > 0).sum(axis=0)
    blocks = []
    for t, origin in enumerate(quarters):
        if t < 3 or (origins is not None and origin not in origins):
            continue
        histories = observed[:, : t + 1].sum(axis=1)
        eligible = histories >= 4
        if not eligible.any():
            continue
        past = clean[eligible, : t + 1]
        seen = observed[eligible, : t + 1]
        n = histories[eligible]
        recent = past[:, -4:]
        last4 = recent.sum(axis=1)
        has_year = n >= 8
        previous4 = past[:, -8:-4].sum(axis=1) if t >= 7 else np.zeros(len(past))
        annual_change = np.where(has_year, last4 - previous4, 0)
        last_active = np.where(past > 0, np.arange(t + 1), -1).max(axis=1)
        base = names.loc[eligible].reset_index(drop=True).copy()
        base["origin"] = origin
        base["history_quarters"] = n
        base["history_mean"] = past.sum(axis=1) / n
        base["history_active_rate"] = (past > 0).sum(axis=1) / n
        base["history_max"] = past.max(axis=1)
        for lag in range(1, 5):
            base[f"cases_recent{lag}"] = past[:, -lag]
        base["cases_last4"] = last4
        base["active_last4"] = (recent > 0).sum(axis=1)
        base["recent_change"] = recent[:, -1] - recent[:, -2]
        base["recent_slope"] = recent @ np.array([-1.5, -0.5, 0.5, 1.5]) / 5
        base["cases_previous4"] = np.where(has_year, previous4, -1)
        base["has_previous_year"] = has_year.astype(int)
        base["annual_change"] = annual_change
        base["annual_growth"] = annual_change / (previous4 + 1)
        base["inactive_quarters"] = t - last_active
        base["market_recent_cases"] = market[t]
        base["market_last4_cases"] = market[t - 3 : t + 1].sum()
        base["market_quarter_change"] = (market[t] - market[t - 1]) / (market[t - 1] + 1)
        market_previous4 = market[t - 7 : t - 3].sum() if t >= 7 else 0
        base["market_annual_growth"] = (
            (market[t - 3 : t + 1].sum() - market_previous4) / (market_previous4 + 1)
            if t >= 7
            else 0
        )
        base["market_has_previous_year"] = int(t >= 7)
        base["market_active_companies"] = market_companies[t]
        base["market_company_change"] = (market_companies[t] - market_companies[t - 1]) / (
            market_companies[t - 1] + 1
        )
        base["company_market_share"] = last4 / max(market[t - 3 : t + 1].sum(), 1)
        for horizon in range(1, 3):
            target = origin + horizon
            block = base.copy()
            block["horizon"] = horizon
            block["target_quarter"] = target
            season = quarters[: t + 1] % 4 == target % 4
            season_n = seen[:, season].sum(axis=1)
            block["same_quarter_observations"] = season_n
            block["same_quarter_last_year"] = past[:, t + horizon - 4]
            block["same_quarter_mean"] = past[:, season].sum(axis=1) / season_n
            block["same_quarter_active_rate"] = (past[:, season] > 0).sum(axis=1) / season_n
            block["market_season_mean"] = market[: t + 1][season].mean()
            for q in range(4):
                block[f"target_q{q + 1}"] = int(target % 4 == q)
            block["target_cases"] = (
                clean[eligible, t + horizon] if t + horizon < len(quarters) else np.nan
            )
            block["target_active"] = (
                block["target_cases"].gt(0).where(block["target_cases"].notna()).astype(float)
            )
            blocks.append(block)
    if not blocks:
        raise ValueError("No companies with four quarters of history")
    result = pd.concat(blocks, ignore_index=True)
    result[FEATURES] = result[FEATURES].astype("float32")
    if not np.isfinite(result[FEATURES].to_numpy()).all():
        raise ValueError("Nonfinite activity features")
    return result


def run(processed_dir: Path) -> dict:
    output_dir = processed_dir / "activity"
    panel = prepare_panel(processed_dir, output_dir)
    frame = pd.read_parquet(output_dir / "company_quarters.parquet")
    examples = build_examples(frame)
    path = output_dir / "examples.parquet"
    examples.to_parquet(path, index=False)
    manifest = {
        **panel,
        "features": FEATURES,
        "feature_code_sha256": sha256(Path(__file__)),
        "examples_sha256": sha256(path),
        "example_rows": len(examples),
        "labeled_rows": int(examples.target_active.notna().sum()),
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {len(examples):,} company-quarter examples to {path}", flush=True)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare inputs for LCA filing probabilities")
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    args = parser.parse_args()
    run(args.processed_dir)


if __name__ == "__main__":
    main()
