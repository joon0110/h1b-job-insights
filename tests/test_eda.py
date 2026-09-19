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
    summary, quarters = eda.profile_companies(company_quarters())
    assert summary["company_quarter_rows"] == 7
    assert summary["lca_cases"] == 10
    assert summary["requested_positions"] == 18
    assert quarters["KNOWN_COMPANIES"].tolist() == [1, 1, 1, 2, 2]
    assert summary["first_four_quarter_companies"] == 1
    assert summary["first_four_zero_case_percent"] == 50
    assert summary["first_four_single_active_quarter_company_percent"] == 0
    assert summary["next_quarter_outcomes"] == {
        "minimum_history_quarters": 4,
        "pairs": 1,
        "companies": 1,
        "no_record": 0,
        "record": 1,
    }


def test_activity_pairs_do_not_jump_over_missing_quarters():
    frame = company_quarters()
    frame.loc[len(frame)] = ["A", "FY2025_Q3", 1, 1, 1]
    summary, quarters = eda.profile_companies(frame)
    assert summary["next_quarter_outcomes"]["pairs"] == 1
    assert quarters.loc["FY2025_Q3", "PREVIOUSLY_ACTIVE_COMPANIES"] == 0
    assert pd.isna(quarters.loc["FY2025_Q3", "PREVIOUSLY_ACTIVE_RATE_PERCENT"])


def test_outcome_charts_share_eligible_pairs_and_exclude_unknown_future():
    frame = company_quarters()
    frame.loc[len(frame)] = ["A", "FY2025_Q2", 0, 0, 0]
    summary, quarters = eda.profile_companies(frame)
    assert summary["next_quarter_outcomes"] == {
        "minimum_history_quarters": 4,
        "pairs": 2,
        "companies": 1,
        "no_record": 1,
        "record": 1,
    }
    assert quarters["PREVIOUSLY_ACTIVE_COMPANIES"].sum() == 1
    assert quarters["PREVIOUSLY_INACTIVE_COMPANIES"].sum() == 1
    assert quarters.loc["FY2025_Q1", "PREVIOUSLY_INACTIVE_RATE_PERCENT"] == 100
    assert quarters.loc["FY2025_Q2", "PREVIOUSLY_ACTIVE_RATE_PERCENT"] == 0
    assert pd.isna(quarters.loc["FY2025_Q1", "PREVIOUSLY_ACTIVE_RATE_PERCENT"])
    assert pd.isna(quarters.loc["FY2024_Q2", "PREVIOUSLY_ACTIVE_RATE_PERCENT"])
    assert "FY2025_Q3" not in quarters.index


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

    receipts, coverage = eda.profile_sources(
        tmp_path,
        [{"release": key} for key in releases],
        date_column="RECEIVED_DATE",
        first_quarter="FY2024_Q1",
        last_quarter="FY2024_Q1",
    )
    assert receipts["date_column"] == "RECEIVED_DATE"
    assert receipts["quarter_totals"] == [
        {"RECEIVED_QUARTER": "FY2024_Q1", "LCA_CASES": 1, "REQUESTED_POSITIONS": 1}
    ]
    assert coverage["H1B_ROWS"].sum() == 4
    assert set(coverage["RECEIVED_QUARTER"]) == {"FY2023_Q4", "FY2024_Q1"}
    eda.check_totals(
        receipts, pd.DataFrame(receipts["quarter_totals"]).set_index("RECEIVED_QUARTER")
    )


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
