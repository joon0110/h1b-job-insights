import pandas as pd
import pytest

from h1b_job_insights import eda


def company_quarters() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("A", "FY2024_Q1", 2, 2, 3),
            ("A", "FY2024_Q2", 0, 0, 0),
            ("A", "FY2024_Q3", 4, 3, 8),
            ("A", "FY2024_Q4", 0, 0, 0),
            ("A", "FY2025_Q1", 3, 3, 5),
            ("B", "FY2024_Q4", 1, 0, 2),
            ("B", "FY2025_Q1", 0, 0, 0),
        ],
        columns=[
            "EMPLOYER_ID",
            "FISCAL_QUARTER",
            "LCA_CASES",
            "CERTIFIED_CASES",
            "REQUESTED_POSITIONS",
        ],
    )


def test_activity_pairs_exclude_unobserved_past_and_future():
    summary, quarters, _ = eda.profile_companies(company_quarters())
    assert summary["company_quarter_rows"] == 7
    assert summary["lca_cases"] == 10
    assert summary["requested_positions"] == 18
    assert summary["zero_case_percent_after_first_record"] == pytest.approx(300 / 7)
    assert summary["active_quarters_without_certified_cases"] == 1
    assert quarters["KNOWN_COMPANIES"].tolist() == [1, 1, 1, 2, 2]
    assert quarters["PREVIOUS_ACTIVE_COMPANIES"].tolist() == [0, 1, 0, 1, 1]
    assert quarters["RETURNING_ACTIVE_COMPANIES"].tolist() == [0, 0, 0, 0, 0]
    assert pd.isna(quarters.loc["FY2024_Q1", "RETURN_RATE_PERCENT"])
    assert quarters.loc["FY2024_Q2", "RETURN_RATE_PERCENT"] == 0
    assert summary["first_four_quarter_companies"] == 1
    assert summary["first_four_zero_case_percent"] == 50
    assert summary["first_four_single_active_quarter_company_percent"] == 0
    assert summary["first_four_case_bands"] == {
        "0": 2,
        "1": 0,
        "2–5": 2,
        "6–20": 0,
        "21–100": 0,
        "101+": 0,
    }
    assert summary["first_four_next_quarter_activity"] == [
        {
            "active_quarters": 2,
            "companies": 1,
            "next_active_companies": 1,
            "next_active_percent": 100.0,
        }
    ]
    one, four, eight = summary["history_candidates"]
    assert one["pairs"] == 5
    assert one["next_active_percent"] == 40
    assert four["pairs"] == 1
    assert four["next_active_percent"] == 100
    assert eight["pairs"] == 0
    assert eight["next_active_percent"] is None
    assert summary["activity_transitions"] == [
        {"current_active": False, "pairs": 2, "next_active_percent": 100.0},
        {"current_active": True, "pairs": 3, "next_active_percent": 0.0},
    ]


def test_activity_pairs_do_not_jump_over_missing_quarters():
    frame = company_quarters()
    frame = frame.loc[frame["FISCAL_QUARTER"].ne("FY2024_Q3")]
    summary, _, _ = eda.profile_companies(frame)
    assert summary["history_candidates"][0]["pairs"] == 3


def test_return_rate_counts_only_prior_quarter_filers():
    frame = company_quarters()
    frame.loc[
        frame["EMPLOYER_ID"].eq("A") & frame["FISCAL_QUARTER"].eq("FY2024_Q2"), "LCA_CASES"
    ] = 1
    _, quarters, _ = eda.profile_companies(frame)
    assert quarters.loc["FY2024_Q2", "RETURN_RATE_PERCENT"] == 100
    assert quarters.loc["FY2024_Q3", "RETURN_RATE_PERCENT"] == 100
    assert quarters.loc["FY2024_Q4", "RETURN_RATE_PERCENT"] == 0


def test_duplicate_company_quarters_fail():
    frame = company_quarters()
    with pytest.raises(ValueError, match="Duplicate company quarters"):
        eda.profile_companies(pd.concat([frame, frame.iloc[:1]]))


def test_source_profile_tracks_revisions_and_keeps_invalid_dates_visible(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    releases = {
        "FY2024_Q1": [
            ("A", "H-1B", "Acme", "Certified", "2023-10-01", "2023-09-26", "2"),
            ("D", "E-3", "Acme", "Certified", "2023-10-02", "2023-09-27", "9"),
            ("C", "H-1B", "Other", "Denied", None, "2023-09-25", "1"),
        ],
        "FY2024_Q2": [
            ("A", "H-1B", "ACME", "Withdrawn", "2024-01-05", "2023-09-26", "5"),
            ("B", "H-1B", "Beta", "Certified", "2023-12-12", "2023-12-10", "1"),
        ],
    }
    for release, rows in releases.items():
        pd.DataFrame(rows, columns=eda.SOURCE_COLUMNS).to_parquet(
            main / f"{release.lower()}.parquet"
        )
    summary, coverage = eda.profile_sources(tmp_path, [{"release": key} for key in releases])
    assert summary["revisions"]["repeated_rows"] == 1
    assert summary["revisions"]["changed_rows"] == 1
    assert summary["revisions"]["decision_quarter_changed_rows"] == 1
    assert summary["h1b_unique_cases"] == 3
    assert summary["statuses"] == {"Withdrawn": 1, "Certified": 1, "Denied": 1}
    assert summary["missing_or_invalid_decision_dates"] == 1
    assert summary["first_selected_release_quarter_offset"] == {"0": 1, "1": 1}
    assert coverage["H1B_ROWS"].sum() == 4
    assert summary["quarter_totals"] == [
        {"DECISION_QUARTER": "FY2024_Q1", "LCA_CASES": 1, "REQUESTED_POSITIONS": 1},
        {"DECISION_QUARTER": "FY2024_Q2", "LCA_CASES": 1, "REQUESTED_POSITIONS": 5},
    ]
    totals = pd.DataFrame(summary["quarter_totals"]).set_index("DECISION_QUARTER")
    eda.check_totals(summary, totals)
    totals.loc["FY2024_Q1", "REQUESTED_POSITIONS"] = 2
    with pytest.raises(ValueError, match="do not match source totals"):
        eda.check_totals(summary, totals)


def test_missing_source_quarter_is_not_treated_as_zero():
    sources = {
        "quarter_totals": [
            {"DECISION_QUARTER": "FY2024_Q1", "LCA_CASES": 1, "REQUESTED_POSITIONS": 1}
        ]
    }
    quarters = pd.DataFrame(
        {"LCA_CASES": [1, 0], "REQUESTED_POSITIONS": [1, 0]},
        index=["FY2024_Q1", "FY2024_Q2"],
    )
    with pytest.raises(ValueError, match="No source records for FY2024_Q2"):
        eda.check_totals(sources, quarters)
