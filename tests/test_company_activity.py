import json
import sqlite3
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from h1b_job_insights import company_activity, normalize
from h1b_job_insights.sources import discover_sources


def write_main(path: Path, rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        name: [row[index] for row in rows]
        for index, name in enumerate(company_activity.INPUT_COLUMNS)
    }
    data["EMPLOYER_FEIN"] = [row[-1] for row in rows]
    pq.write_table(pa.Table.from_pydict(data), path)


def test_company_counts_use_names_and_latest_case_version(tmp_path: Path) -> None:
    processed = tmp_path / "processed"
    files = []
    releases = {
        "FY2024_Q1": [
            ("A", "Certified", "H-1B", "2023-10-05", "Acme, LLC", "2", "11-1111111"),
            ("B", "Certified", "H-1B", "2023-10-06", "ACME LLC", "3", "22-2222222"),
            ("D", "Certified", "E-3", "2023-10-07", "Acme LLC", "100", None),
        ],
        "FY2024_Q2": [
            ("A", "Withdrawn", "H-1B", "2024-01-10", "ACME L.L.C.", "6", "11-1111111"),
            ("E", "Certified", "H-1B", "2024-01-11", "Acme LLC", "4", "33-3333333"),
            ("F", "Certified", "H-1B", None, "Acme LLC", "5", None),
            ("C", "Denied", "H-1B", "2024-01-12", "Other Inc", "1", None),
        ],
        "FY2024_Q4": [
            ("G", "Certified", "H-1B", "2024-07-01", "Other Inc", "1", None),
        ],
    }
    for release, rows in releases.items():
        write_main(processed / "main" / f"{release.lower()}.parquet", rows)
        files.append(
            {
                "release": release,
                "kind": "main",
                "sha256": release,
                "sheets": [{"data_rows": len(rows)}],
            }
        )
    processed.mkdir(exist_ok=True)
    (processed / "source_manifest.json").write_text(json.dumps({"files": files}))

    quality = company_activity.run(processed)
    assert quality["repeated_case_rows"] == 1
    assert quality["h1b_cases"] == 6
    assert quality["h1b_cases_with_company_and_date"] == 5
    assert quality["requested_positions"] == 15
    assert quality["companies"] == 2

    path = processed / "company_activity" / "company_quarters.parquet"
    company_id = normalize.employer_id(normalize.employer_name("Acme LLC"))
    rows = pq.read_table(path, filters=[("EMPLOYER_ID", "=", company_id)]).to_pylist()
    assert [row["FISCAL_QUARTER"] for row in rows] == [
        "FY2024_Q1",
        "FY2024_Q2",
        "FY2024_Q3",
        "FY2024_Q4",
    ]
    assert [row["LCA_CASES"] for row in rows] == [1, 2, 0, 0]
    assert [row["CERTIFIED_CASES"] for row in rows] == [1, 1, 0, 0]
    assert [row["CHANGE_FROM_PREVIOUS_QUARTER"] for row in rows] == [None, 1, -2, 0]
    assert [row["CHANGE_PERCENT"] for row in rows] == [None, 100.0, -100.0, None]
    assert [row["REQUESTED_POSITIONS"] for row in rows] == [3, 10, 0, 0]
    assert [row["POSITION_CHANGE_FROM_PREVIOUS_QUARTER"] for row in rows] == [None, 7, -10, 0]
    assert [row["POSITION_CHANGE_PERCENT"] for row in rows] == [None, 233.33, -100.0, None]

    other_id = normalize.employer_id(normalize.employer_name("Other Inc"))
    other_rows = pq.read_table(path, filters=[("EMPLOYER_ID", "=", other_id)]).to_pylist()
    assert [row["FISCAL_QUARTER"] for row in other_rows] == [
        "FY2024_Q2",
        "FY2024_Q3",
        "FY2024_Q4",
    ]
    assert other_rows[0]["CHANGE_FROM_PREVIOUS_QUARTER"] is None
    assert other_rows[0]["POSITION_CHANGE_FROM_PREVIOUS_QUARTER"] is None


def test_invalid_requested_positions_fail_with_case_number(tmp_path: Path) -> None:
    path = tmp_path / "main.parquet"
    write_main(path, [("A", "Certified", "H-1B", "2024-01-01", "Acme", "bad", None)])
    db = sqlite3.connect(":memory:")
    with pytest.raises(ValueError, match="TOTAL_WORKER_POSITIONS.*case A"):
        company_activity.load_cases(db, path)


def test_main_source_discovery_ignores_worksites(tmp_path: Path) -> None:
    (tmp_path / "LCA_Disclosure_Data_FY2027_Q1.xlsx").touch()
    (tmp_path / "LCA_Worksites_FY2027_Q1.xlsx").touch()
    found = discover_sources(tmp_path)
    assert [(item.release, item.kind) for item in found] == [("FY2027_Q1", "main")]


def test_company_name_does_not_drop_legal_suffix() -> None:
    assert normalize.employer_name(" Acme, L.L.C. ") == "ACME LLC"
    assert normalize.employer_name("ACME INC") != normalize.employer_name("ACME LLC")
