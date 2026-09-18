import argparse
import json
import math
import os
from pathlib import Path

import pandas as pd

from h1b_job_insights import company_activity, normalize

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


def profile_sources(processed_dir: Path, files: list[dict]) -> tuple[dict, pd.DataFrame]:
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
    h1b_raw["DECISION_QUARTER"] = quarter_labels(parse_dates(h1b_raw["DECISION_DATE"]))
    coverage = (
        h1b_raw.groupby(["RELEASE", "DECISION_QUARTER"], dropna=False)
        .size()
        .rename("H1B_ROWS")
        .reset_index()
    )
    first = raw.drop_duplicates("CASE_NUMBER", keep="first")
    first = first.loc[first["VISA_CLASS"].eq("H-1B")]
    first_quarters = quarter_labels(parse_dates(first["DECISION_DATE"]))
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
    counted = decisions.notna() & latest["EMPLOYER_NAME"].map(names).notna()
    latest["DECISION_QUARTER"] = quarter_labels(decisions)
    latest["POSITIONS"] = pd.to_numeric(latest["TOTAL_WORKER_POSITIONS"], errors="raise")
    totals = (
        latest.loc[counted]
        .groupby("DECISION_QUARTER")
        .agg(LCA_CASES=("CASE_NUMBER", "size"), REQUESTED_POSITIONS=("POSITIONS", "sum"))
    )
    summary = {
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


def profile_companies(frame: pd.DataFrame) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    frame = frame.sort_values(["EMPLOYER_ID", "FISCAL_QUARTER"]).copy()
    if frame.empty:
        raise ValueError("No company quarters to analyze")
    if frame.duplicated(["EMPLOYER_ID", "FISCAL_QUARTER"]).any():
        raise ValueError("Duplicate company quarters")
    frame["ACTIVE"] = frame["LCA_CASES"].gt(0)
    grouped = frame.groupby("EMPLOYER_ID", sort=False)
    companies = grouped.agg(
        LCA_CASES=("LCA_CASES", "sum"),
        REQUESTED_POSITIONS=("REQUESTED_POSITIONS", "sum"),
        OBSERVED_QUARTERS=("FISCAL_QUARTER", "size"),
        ACTIVE_QUARTERS=("ACTIVE", "sum"),
    )
    frame["HISTORY_QUARTERS"] = grouped.cumcount() + 1
    frame["NEW_COMPANY"] = frame["HISTORY_QUARTERS"].eq(1)
    quarters = frame.groupby("FISCAL_QUARTER", sort=True).agg(
        LCA_CASES=("LCA_CASES", "sum"),
        CERTIFIED_CASES=("CERTIFIED_CASES", "sum"),
        REQUESTED_POSITIONS=("REQUESTED_POSITIONS", "sum"),
        KNOWN_COMPANIES=("EMPLOYER_ID", "size"),
        ACTIVE_COMPANIES=("ACTIVE", "sum"),
        NEW_COMPANIES=("NEW_COMPANY", "sum"),
    )
    frame["NEXT_CASES"] = grouped["LCA_CASES"].shift(-1)
    next_quarter = grouped["FISCAL_QUARTER"].shift(-1)
    next_index = next_quarter.map(lambda value: quarter_number(value) if pd.notna(value) else None)
    adjacent = next_index.eq(frame["FISCAL_QUARTER"].map(quarter_number) + 1)
    pairs = frame.loc[adjacent & frame["NEXT_CASES"].notna()].copy()
    pairs["NEXT_ACTIVE"] = pairs["NEXT_CASES"].gt(0)
    previous_active = pairs.loc[pairs["ACTIVE"]]
    returning = previous_active.groupby(next_quarter.loc[previous_active.index])["NEXT_ACTIVE"].agg(
        ["size", "sum"]
    )
    quarters["PREVIOUS_ACTIVE_COMPANIES"] = returning["size"].reindex(quarters.index, fill_value=0)
    quarters["RETURNING_ACTIVE_COMPANIES"] = returning["sum"].reindex(quarters.index, fill_value=0)
    quarters["RETURN_RATE_PERCENT"] = (
        100 * quarters["RETURNING_ACTIVE_COMPANIES"] / quarters["PREVIOUS_ACTIVE_COMPANIES"]
    ).where(quarters["PREVIOUS_ACTIVE_COMPANIES"].gt(0))
    history = []
    for minimum in (1, 4, 8):
        eligible = pairs.loc[pairs["HISTORY_QUARTERS"].ge(minimum)]
        history.append(
            {
                "minimum_history_quarters": minimum,
                "pairs": len(eligible),
                "companies": int(eligible["EMPLOYER_ID"].nunique()),
                "pair_coverage_percent": 100 * len(eligible) / len(pairs) if len(pairs) else None,
                "next_active_percent": 100 * float(eligible["NEXT_ACTIVE"].mean())
                if len(eligible)
                else None,
            }
        )
    transitions = []
    for active, group in pairs.groupby("ACTIVE"):
        transitions.append(
            {
                "current_active": bool(active),
                "pairs": len(group),
                "next_active_percent": 100 * float(group["NEXT_ACTIVE"].mean()),
            }
        )
    top_n = max(1, math.ceil(len(companies) * 0.01))
    concentration = {
        metric: 100
        * float(companies[metric].nlargest(top_n).sum())
        / float(companies[metric].sum())
        for metric in ("LCA_CASES", "REQUESTED_POSITIONS")
    }
    first_four_companies = companies.loc[companies["OBSERVED_QUARTERS"].ge(4)]
    first_four = frame.loc[
        frame["HISTORY_QUARTERS"].le(4) & frame["EMPLOYER_ID"].isin(first_four_companies.index)
    ]
    first_four_active = first_four.groupby("EMPLOYER_ID")["ACTIVE"].sum()
    fifth_quarter = pairs.loc[pairs["HISTORY_QUARTERS"].eq(4), ["EMPLOYER_ID", "NEXT_ACTIVE"]].join(
        first_four_active.rename("ACTIVE_IN_FIRST_FOUR"), on="EMPLOYER_ID"
    )
    next_activity = fifth_quarter.groupby("ACTIVE_IN_FIRST_FOUR")["NEXT_ACTIVE"].agg(
        ["size", "sum"]
    )
    case_bands = pd.cut(
        first_four["LCA_CASES"],
        bins=[-1, 0, 1, 5, 20, 100, float("inf")],
        labels=["0", "1", "2–5", "6–20", "21–100", "101+"],
    ).value_counts(sort=False)
    summary = {
        "first_quarter": str(quarters.index.min()),
        "last_quarter": str(quarters.index.max()),
        "quarters": len(quarters),
        "companies": len(companies),
        "company_quarter_rows": len(frame),
        "lca_cases": int(frame["LCA_CASES"].sum()),
        "requested_positions": int(frame["REQUESTED_POSITIONS"].sum()),
        "zero_case_percent_after_first_record": 100 * float((~frame["ACTIVE"]).mean()),
        "active_quarters_without_certified_cases": int(
            (frame["ACTIVE"] & frame["CERTIFIED_CASES"].eq(0)).sum()
        ),
        "single_active_quarter_company_percent_through_last_release": 100
        * float(companies["ACTIVE_QUARTERS"].eq(1).mean()),
        "first_four_quarter_companies": len(first_four_companies),
        "first_four_zero_case_percent": 100 * float((~first_four["ACTIVE"]).mean()),
        "first_four_single_active_quarter_company_percent": 100
        * float(first_four_active.eq(1).mean()),
        "company_lca_cases": distribution(companies["LCA_CASES"]),
        "company_requested_positions": distribution(companies["REQUESTED_POSITIONS"]),
        "active_quarters_per_company": distribution(companies["ACTIVE_QUARTERS"]),
        "top_one_percent_companies": top_n,
        "top_one_percent_share": concentration,
        "first_four_case_bands": {str(key): int(value) for key, value in case_bands.items()},
        "first_four_active_quarters": {
            str(int(key)): int(value)
            for key, value in first_four_active.value_counts().sort_index().items()
        },
        "first_four_next_quarter_activity": [
            {
                "active_quarters": int(active_quarters),
                "companies": int(row["size"]),
                "next_active_companies": int(row["sum"]),
                "next_active_percent": 100 * float(row["sum"]) / float(row["size"]),
            }
            for active_quarters, row in next_activity.iterrows()
        ],
        "history_candidates": history,
        "activity_transitions": transitions,
    }
    return summary, quarters, companies


def check_totals(sources: dict, quarters: pd.DataFrame) -> None:
    expected = pd.DataFrame(sources["quarter_totals"]).set_index("DECISION_QUARTER")
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
    companies_line = ax.plot(
        x, quarters["ACTIVE_COMPANIES"], marker="o", color="#287b68", label="Companies"
    )[0]
    ax.set(title="Companies and requested positions by quarter", ylabel="Companies", ylim=(0, None))
    ax.set_xticks(list(x)[::2], list(quarters.index)[::2], rotation=35, ha="right")
    ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    ax.tick_params(axis="y", colors="#287b68")
    positions_ax = ax.twinx()
    positions_line = positions_ax.plot(
        x,
        quarters["REQUESTED_POSITIONS"],
        marker="s",
        linestyle="--",
        color="#b27548",
        label="Requested positions",
    )[0]
    positions_ax.set(ylabel="Requested positions", ylim=(0, None))
    positions_ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    positions_ax.tick_params(axis="y", colors="#b27548")
    ax.legend(handles=[companies_line, positions_line], loc="upper left", frameon=False)

    ax = axes[0, 1]
    history = summary["first_four_active_quarters"]
    bars = ax.bar([int(key) for key in history], list(history.values()), color="#b27548")
    ax.set(
        title="Company activity in its first four observed quarters",
        xlabel="Quarters with at least one case",
        ylabel="Companies",
        ylim=(0, max(history.values()) * 1.12),
    )
    ax.set_xticks([1, 2, 3, 4])
    ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    ax.bar_label(bars, labels=[f"{value:,}" for value in history.values()], padding=3)

    ax = axes[1, 0]
    return_rate = quarters["RETURN_RATE_PERCENT"]
    ax.plot(x, return_rate, marker="o", color="#526e9d")
    ax.set(
        title="Companies filing again from the previous quarter",
        ylabel="Previous quarter's companies (%)",
        ylim=(0, 100),
    )
    ax.set_xticks(list(x)[1::2], list(quarters.index)[1::2], rotation=35, ha="right")

    ax = axes[1, 1]
    case_bands = summary["first_four_case_bands"]
    bars = ax.bar(list(case_bands), list(case_bands.values()), color="#8b6c9a")
    ax.set(
        title="LCA cases per company-quarter in the first four quarters",
        xlabel="LCA cases in a quarter",
        ylabel="Company-quarter rows",
        ylim=(0, max(case_bands.values()) * 1.12),
    )
    ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    ax.bar_label(bars, labels=[f"{value:,}" for value in case_bands.values()], padding=3)

    for ax in axes.flat:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
    fig.suptitle("H-1B LCA activity by employer name", fontsize=16)
    fig.supxlabel(
        "First four quarters start with each company's first record. "
        "FY2022 Q1 has no previous quarter for the repeat rate.",
        fontsize=9,
    )
    fig.savefig(path, dpi=160)
    plt.close(fig)


def run(processed_dir: Path, output_dir: Path) -> dict:
    company_activity.run(processed_dir)
    manifest = json.loads((processed_dir / "source_manifest.json").read_text())
    files = [item for item in manifest["files"] if item["kind"] == "main"]
    print("Checking source dates, statuses, and revisions", flush=True)
    sources, coverage = profile_sources(processed_dir, files)
    frame = pd.read_parquet(
        processed_dir / "company_activity" / "company_quarters.parquet", dtype_backend="pyarrow"
    )
    summary, quarters, _ = profile_companies(frame)
    check_totals(sources, quarters)
    summary["sources"] = sources
    summary["source_versions"] = [
        {key: item[key] for key in ("release", "sha256")} for item in files
    ]
    summary["availability"] = {
        "publication_dates_verified": False,
        "basis": "Latest selected case versions; release quarters are not publication dates.",
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
