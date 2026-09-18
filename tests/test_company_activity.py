import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

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
            ("A", "Certified", "H-1B", "2023-10-05", "Acme, LLC", "11-1111111"),
            ("B", "Certified", "H-1B", "2023-10-06", "ACME LLC", "22-2222222"),
            ("C", "Denied", "H-1B", "2023-10-07", "Other Inc", None),
            ("D", "Certified", "E-3", "2023-10-07", "Acme LLC", None),
        ],
        "FY2024_Q2": [
            ("A", "Withdrawn", "H-1B", "2024-01-10", "ACME L.L.C.", "11-1111111"),
            ("E", "Certified", "H-1B", "2024-01-11", "Acme LLC", "33-3333333"),
            ("F", "Certified", "H-1B", None, "Acme LLC", None),
        ],
        "FY2024_Q4": [
            ("G", "Certified", "H-1B", "2024-07-01", "Other Inc", None),
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


def test_main_source_discovery_ignores_worksites(tmp_path: Path) -> None:
    (tmp_path / "LCA_Disclosure_Data_FY2027_Q1.xlsx").touch()
    (tmp_path / "LCA_Worksites_FY2027_Q1.xlsx").touch()
    found = discover_sources(tmp_path)
    assert [(item.release, item.kind) for item in found] == [("FY2027_Q1", "main")]


def test_company_name_does_not_drop_legal_suffix() -> None:
    assert normalize.employer_name(" Acme, L.L.C. ") == "ACME LLC"
    assert normalize.employer_name("ACME INC") != normalize.employer_name("ACME LLC")
