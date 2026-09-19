import argparse
import json
import os
from pathlib import Path

import pandas as pd

from h1b_job_insights import activity_data, normalize

SOURCE_COLUMNS = [
    "CASE_NUMBER",
    "VISA_CLASS",
    "EMPLOYER_NAME",
    "CASE_STATUS",
    "DECISION_DATE",
    "RECEIVED_DATE",
    "TOTAL_WORKER_POSITIONS",
]


def quarter_number(label: str) -> int:
    return int(label[2:6]) * 4 + int(label[-1]) - 1


def parse_dates(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values.astype("string").str[:10], format="%Y-%m-%d", errors="coerce")


def quarter_labels(dates: pd.Series) -> pd.Series:
    periods = dates.dt.to_period("Q-SEP")
    labels = "FY" + periods.dt.qyear.astype("string") + "_Q" + periods.dt.quarter.astype("string")
    return labels.where(dates.notna())


def distribution(values: pd.Series) -> dict:
    values = values.dropna()
    if values.empty:
        return {}
    return {
        "mean": float(values.mean()),
        **{
            name: float(values.quantile(q))
            for name, q in [("min", 0), ("median", 0.5), ("p90", 0.9), ("p99", 0.99), ("max", 1)]
        },
    }


def profile_sources(
    processed_dir: Path,
    files: list[dict],
    date_column: str = "DECISION_DATE",
    first_quarter: str | None = None,
    last_quarter: str | None = None,
) -> tuple[dict, pd.DataFrame]:
    if date_column not in {"DECISION_DATE", "RECEIVED_DATE"}:
        raise ValueError(f"Unsupported date column: {date_column}")
    quarter_column = date_column.replace("_DATE", "_QUARTER")
    frames = []
    for item in sorted(files, key=lambda item: item["release"]):
        path = processed_dir / "main" / f"{item['release'].lower()}.parquet"
        frame = pd.read_parquet(path, columns=SOURCE_COLUMNS, dtype_backend="pyarrow")
        frame["RELEASE"] = item["release"]
        frames.append(frame)
    raw = pd.concat(frames, ignore_index=True)
    raw["CASE_NUMBER"] = raw["CASE_NUMBER"].str.strip().str.upper()
    raw["VISA_CLASS"] = raw["VISA_CLASS"].str.strip().str.upper()
    raw["CASE_STATUS"] = raw["CASE_STATUS"].str.strip()
    valid_case = raw["CASE_NUMBER"].notna() & raw["CASE_NUMBER"].ne("")
    rows_without_case = int((~valid_case).sum())
    raw = raw.loc[valid_case]

    repeated = raw.loc[raw["CASE_NUMBER"].duplicated(keep=False)]
    previous = repeated.groupby("CASE_NUMBER", sort=False)[SOURCE_COLUMNS[1:]].shift()
    updates = repeated["CASE_NUMBER"].duplicated()
    changes = repeated[SOURCE_COLUMNS[1:]].fillna("").ne(previous.fillna(""))
    changed_quarters = (
        quarter_labels(parse_dates(repeated["DECISION_DATE"]))
        .fillna("")
        .ne(quarter_labels(parse_dates(previous["DECISION_DATE"])).fillna(""))
    )
    revisions = {
        "repeated_rows": int(updates.sum()),
        "changed_rows": int((changes.any(axis=1) & updates).sum()),
        "h1b_changed_rows": int(
            (changes.any(axis=1) & updates & repeated["VISA_CLASS"].eq("H-1B")).sum()
        ),
        "decision_quarter_changed_rows": int((changed_quarters & updates).sum()),
        "changed_fields": {
            name: int((changes[name] & updates).sum()) for name in SOURCE_COLUMNS[1:]
        },
    }

    h1b_raw = raw.loc[raw["VISA_CLASS"].eq("H-1B")].copy()
    h1b_raw[quarter_column] = quarter_labels(parse_dates(h1b_raw[date_column]))
    coverage = (
        h1b_raw.groupby(["RELEASE", quarter_column], dropna=False)
        .size()
        .rename("H1B_ROWS")
        .reset_index()
    )
    first = raw.drop_duplicates("CASE_NUMBER", keep="first")
    first = first.loc[first["VISA_CLASS"].eq("H-1B")]
    first_quarters = quarter_labels(parse_dates(first[date_column]))
    offsets = first["RELEASE"].map(quarter_number) - first_quarters.map(
        lambda value: quarter_number(value) if pd.notna(value) else None
    )

    latest = raw.drop_duplicates("CASE_NUMBER", keep="last")
    latest = latest.loc[latest["VISA_CLASS"].eq("H-1B")].copy()
    decisions = parse_dates(latest["DECISION_DATE"])
    received = parse_dates(latest["RECEIVED_DATE"])
    elapsed = (decisions - received).dt.days
    names = {
        name: normalize.employer_name(name) for name in latest["EMPLOYER_NAME"].dropna().unique()
    }
    dates = received if date_column == "RECEIVED_DATE" else decisions
    counted = dates.notna() & latest["EMPLOYER_NAME"].map(names).notna()
    latest[quarter_column] = quarter_labels(dates)
    if first_quarter is not None:
        counted &= latest[quarter_column].ge(first_quarter)
    if last_quarter is not None:
        counted &= latest[quarter_column].le(last_quarter)
    latest["POSITIONS"] = pd.to_numeric(latest["TOTAL_WORKER_POSITIONS"], errors="raise")
    totals = (
        latest.loc[counted]
        .groupby(quarter_column)
        .agg(LCA_CASES=("CASE_NUMBER", "size"), REQUESTED_POSITIONS=("POSITIONS", "sum"))
    )
    summary = {
        "date_column": date_column,
        "quarter_column": quarter_column,
        "rows_without_case_number": rows_without_case,
        "revisions": revisions,
        "h1b_unique_cases": len(latest),
        "statuses": {
            str(key): int(value)
            for key, value in latest["CASE_STATUS"].fillna("<missing>").value_counts().items()
        },
        "decision_date_min": str(decisions.min().date()) if decisions.notna().any() else None,
        "decision_date_max": str(decisions.max().date()) if decisions.notna().any() else None,
        "missing_or_invalid_decision_dates": int(decisions.isna().sum()),
        "missing_or_invalid_received_dates": int(received.isna().sum()),
        "decision_before_received": int(elapsed.lt(0).sum()),
        "received_to_decision_days": distribution(elapsed),
        "requested_positions_per_case": distribution(latest["POSITIONS"]),
        "first_selected_release_quarter_offset": {
            str(int(key)): int(value) for key, value in offsets.value_counts().sort_index().items()
        },
        "quarter_totals": json.loads(totals.reset_index().to_json(orient="records")),
    }
    return summary, coverage


def profile_companies(frame: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    frame = frame.sort_values(["EMPLOYER_ID", "FISCAL_QUARTER"]).copy()
    if frame.empty:
        raise ValueError("No company quarters to analyze")
    if frame.duplicated(["EMPLOYER_ID", "FISCAL_QUARTER"]).any():
        raise ValueError("Duplicate company quarters")
    frame["ACTIVE"] = frame["LCA_CASES"].gt(0)
    grouped = frame.groupby("EMPLOYER_ID", sort=False)
    companies = grouped.size()
    frame["HISTORY_QUARTERS"] = grouped.cumcount() + 1
    quarters = frame.groupby("FISCAL_QUARTER", sort=True).agg(
        LCA_CASES=("LCA_CASES", "sum"),
        CERTIFIED_CASES=("CERTIFIED_CASES", "sum"),
        REQUESTED_POSITIONS=("REQUESTED_POSITIONS", "sum"),
        KNOWN_COMPANIES=("EMPLOYER_ID", "size"),
        ACTIVE_COMPANIES=("ACTIVE", "sum"),
    )
    frame["NEXT_CASES"] = grouped["LCA_CASES"].shift(-1)
    next_quarter = grouped["FISCAL_QUARTER"].shift(-1)
    next_index = next_quarter.map(lambda value: quarter_number(value) if pd.notna(value) else None)
    adjacent = next_index.eq(frame["FISCAL_QUARTER"].map(quarter_number) + 1)
    pairs = frame.loc[adjacent & frame["NEXT_CASES"].notna()].copy()
    pairs["NEXT_ACTIVE"] = pairs["NEXT_CASES"].gt(0)
    eligible_pairs = pairs.loc[pairs["HISTORY_QUARTERS"].ge(4)]
    for active, prefix in ((True, "PREVIOUSLY_ACTIVE"), (False, "PREVIOUSLY_INACTIVE")):
        group = eligible_pairs.loc[eligible_pairs["ACTIVE"].eq(active)]
        outcomes = group.groupby(next_quarter.loc[group.index])["NEXT_ACTIVE"].agg(["size", "sum"])
        quarters[f"{prefix}_COMPANIES"] = outcomes["size"].reindex(quarters.index, fill_value=0)
        quarters[f"{prefix}_NEXT_ACTIVE"] = outcomes["sum"].reindex(quarters.index, fill_value=0)
        quarters[f"{prefix}_RATE_PERCENT"] = (
            100 * quarters[f"{prefix}_NEXT_ACTIVE"] / quarters[f"{prefix}_COMPANIES"]
        ).where(quarters[f"{prefix}_COMPANIES"].gt(0))
    first_four_companies = companies.loc[companies.ge(4)]
    first_four = frame.loc[
        frame["HISTORY_QUARTERS"].le(4) & frame["EMPLOYER_ID"].isin(first_four_companies.index)
    ]
    first_four_active = first_four.groupby("EMPLOYER_ID")["ACTIVE"].sum()
    summary = {
        "first_quarter": str(quarters.index.min()),
        "last_quarter": str(quarters.index.max()),
        "quarters": len(quarters),
        "companies": len(companies),
        "company_quarter_rows": len(frame),
        "lca_cases": int(frame["LCA_CASES"].sum()),
        "requested_positions": int(frame["REQUESTED_POSITIONS"].sum()),
        "first_four_quarter_companies": len(first_four_companies),
        "first_four_zero_case_percent": 100 * float((~first_four["ACTIVE"]).mean()),
        "first_four_single_active_quarter_company_percent": 100
        * float(first_four_active.eq(1).mean()),
        "next_quarter_outcomes": {
            "minimum_history_quarters": 4,
            "pairs": len(eligible_pairs),
            "companies": int(eligible_pairs["EMPLOYER_ID"].nunique()),
            "no_record": int((~eligible_pairs["NEXT_ACTIVE"]).sum()),
            "record": int(eligible_pairs["NEXT_ACTIVE"].sum()),
        },
        "first_four_active_quarters": {
            str(int(key)): int(value)
            for key, value in first_four_active.value_counts().sort_index().items()
        },
    }
    return summary, quarters


def check_totals(sources: dict, quarters: pd.DataFrame) -> None:
    expected = pd.DataFrame(sources["quarter_totals"]).set_index(
        sources.get("quarter_column", "DECISION_QUARTER")
    )
    missing = quarters.index.difference(expected.index)
    if len(missing):
        raise ValueError(f"No source records for {', '.join(missing)}; cannot assume zero activity")
    for metric in ("LCA_CASES", "REQUESTED_POSITIONS"):
        source = expected[metric].reindex(quarters.index, fill_value=0)
        if not source.eq(quarters[metric]).all() or not expected.index.isin(quarters.index).all():
            raise ValueError(f"Company quarters do not match source totals: {metric}")


def plot_overview(summary: dict, quarters: pd.DataFrame, path: Path) -> None:
    os.environ.setdefault("MPLCONFIGDIR", str(path.parent / ".matplotlib"))
    os.environ.setdefault("XDG_CACHE_HOME", str(path.parent / ".cache"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import StrMethodFormatter

    fig, axes = plt.subplots(2, 2, figsize=(15, 9), layout="constrained")
    ax = axes[0, 0]
    x = range(len(quarters))
    labels = quarters.index.str.replace("_", " ")
    ax.plot(x, quarters["ACTIVE_COMPANIES"], marker="o", color="#287b68")
    ax.set(
        title="1. How many companies filed each quarter?",
        xlabel="Receipt quarter",
        ylabel="Companies with at least one LCA",
        ylim=(0, None),
    )
    ax.set_xticks(list(x)[::2], labels[::2], rotation=35, ha="right")
    ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))

    ax = axes[0, 1]
    history = summary["first_four_active_quarters"]
    counts = [history.get(str(q), 0) for q in range(1, 5)]
    bars = ax.bar(range(1, 5), counts, color="#b27548")
    ax.set(
        title="2. How often did a company file in its first four quarters?",
        xlabel="Quarters with at least one LCA (out of 4)",
        ylabel="Companies with four observed quarters",
        ylim=(0, max(1, max(counts)) * 1.15),
    )
    ax.set_xticks([1, 2, 3, 4])
    ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    ax.bar_label(bars, labels=[f"{value:,}" for value in counts], padding=3)

    ax = axes[1, 0]
    included = (
        quarters["PREVIOUSLY_ACTIVE_COMPANIES"] + quarters["PREVIOUSLY_INACTIVE_COMPANIES"]
    ).gt(0)
    outcomes = quarters.loc[included]
    outcome_x = range(len(outcomes))
    for prefix, label, color in (
        ("PREVIOUSLY_ACTIVE", "Filed in previous quarter", "#526e9d"),
        ("PREVIOUSLY_INACTIVE", "No filing in previous quarter", "#b27548"),
    ):
        ax.plot(outcome_x, outcomes[f"{prefix}_RATE_PERCENT"], marker="o", color=color, label=label)
    ax.set(
        title="3. Did companies file in the following quarter?",
        xlabel="Outcome quarter (at least 4 quarters of prior history)",
        ylabel="Companies with a filing (%)",
        ylim=(0, 100),
    )
    ax.set_xticks(
        list(outcome_x)[::2],
        outcomes.index.str.replace("_", " ")[::2],
        rotation=35,
        ha="right",
    )
    ax.legend(loc="upper left", frameon=False, fontsize=9)

    ax = axes[1, 1]
    outcomes = summary["next_quarter_outcomes"]
    counts = [outcomes["no_record"], outcomes["record"]]
    bars = ax.bar(
        ["No record (0)", "At least one record (1)"], counts, color=["#8b6c9a", "#287b68"]
    )
    ax.set(
        title="4. What happened in the next quarter?",
        xlabel="At least 4 quarters of prior history; known outcomes only",
        ylabel="Company-quarter pairs",
        ylim=(0, max(1, max(counts)) * 1.18),
    )
    ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    bar_labels = [
        f"{value:,} ({100 * value / outcomes['pairs']:.1f}%)" if outcomes["pairs"] else "0"
        for value in counts
    ]
    ax.bar_label(bars, labels=bar_labels, padding=3)

    for ax in axes.flat:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
    first = summary["first_quarter"].replace("_", " ")
    last = summary["last_quarter"].replace("_", " ")
    fig.suptitle(
        f"H-1B LCA filing history by employer name\nReceipt dates | {first}–{last}", fontsize=16
    )
    fig.supxlabel(
        "Panel 2 starts at each company's first observed filing. "
        "Panels 3–4 use the same eligible pairs; rates describe history, not model predictions.\n"
        "Latest case versions are used, including the latest source quarter. "
        "Later releases may revise receipt counts.",
        fontsize=9,
    )
    fig.savefig(path, dpi=160)
    plt.close(fig)


def run(processed_dir: Path, output_dir: Path) -> dict:
    panel_dir = processed_dir / "activity"
    panel = activity_data.prepare_panel(processed_dir, panel_dir)
    manifest = json.loads((processed_dir / "source_manifest.json").read_text())
    files = [item for item in manifest["files"] if item["kind"] == "main"]
    print("Checking source dates, statuses, and revisions", flush=True)
    sources, coverage = profile_sources(
        processed_dir,
        files,
        date_column="RECEIVED_DATE",
        first_quarter=panel["first_quarter"],
        last_quarter=panel["last_quarter"],
    )
    frame = pd.read_parquet(panel_dir / "company_quarters.parquet", dtype_backend="pyarrow")
    summary, quarters = profile_companies(frame)
    check_totals(sources, quarters)
    summary["sources"] = sources
    summary["date_column"] = panel["date_column"]
    summary["source_versions"] = [
        {key: item[key] for key in ("release", "sha256")} for item in files
    ]
    summary["availability"] = {
        "publication_dates_verified": False,
        "basis": "Latest selected case versions; release quarters are not publication dates.",
        "latest_source_release": panel["latest_source_release"],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    quarters.to_csv(output_dir / "quarters.csv", float_format="%.2f")
    coverage.to_csv(output_dir / "source_coverage.csv", index=False)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    plot_overview(summary, quarters, output_dir / "overview.png")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze company H-1B LCA history")
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/eda"))
    args = parser.parse_args()
    summary = run(args.processed_dir, args.output_dir)
    print(f"{summary['companies']:,} companies across {summary['quarters']} quarters")
    print(
        f"{summary['first_four_zero_case_percent']:.1f}% of quarters in companies' "
        "first four have no LCA cases"
    )
    print(f"Results in {args.output_dir}")


if __name__ == "__main__":
    main()
