import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest
from openpyxl import Workbook

from h1b_job_insights import pipeline, schema
from h1b_job_insights.pipeline import inspect, run
from h1b_job_insights.sources import Source

MAIN_HEADERS = (
    "CASE_NUMBER",
    "CASE_STATUS",
    "RECEIVED_DATE",
    "DECISION_DATE",
    "ORIGINAL_CERT_DATE",
    "VISA_CLASS",
    "EMPLOYER_NAME",
    "SOC_CODE",
    "WORKSITE_CITY",
    "WORKSITE_STATE",
    "WORKSITE_POSTAL_CODE",
)
WORKSITE_HEADERS = (
    "CASE_NUMBER",
    "WORKSITE_CITY",
    "WORKSITE_STATE",
    "WORKSITE_POSTAL_CODE",
    "WORKSITE_WORKERS",
)


def workbook(path: Path, headers: tuple[str, ...], rows: list[tuple]) -> None:
    book = Workbook()
    sheet = book.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    book.save(path)


def source(release: str, kind: str, filename: str) -> Source:
    return Source(release, kind, f"https://example.test/{filename}")


def test_missing_required_header_fails(tmp_path: Path) -> None:
    item = source("FY2022_Q2", "main", "missing.xlsx")
    path = tmp_path / item.filename
    workbook(path, MAIN_HEADERS[:-1], [])

    with pytest.raises(ValueError, match="WORKSITE_POSTAL_CODE"):
        inspect(item, path)


def test_missing_local_file_is_reported(tmp_path: Path) -> None:
    item = source("FY2022_Q1", "main", "missing.xlsx")

    with pytest.raises(FileNotFoundError, match="missing.xlsx"):
        run(tmp_path, tmp_path / "processed", (item,))


def test_new_quarter_uses_the_fixed_schema(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    filename = "LCA_Disclosure_Data_FY2027_Q1.xlsx"
    workbook(
        raw / filename,
        tuple(header.lower().replace("_", " ") for header in MAIN_HEADERS)
        + ("H-1B_DEPENDENT",),
        [
            (
                "E",
                "Certified",
                "2026-10-01",
                "2026-10-02",
                None,
                "H-1B",
                "Acme",
                "15-2051",
                "New York",
                "NY",
                "10001",
                "Yes",
            )
        ],
    )

    report = run(raw, tmp_path / "processed")

    assert report["main"][0]["source_rows"] == 1
    manifest = json.loads((tmp_path / "processed" / "source_manifest.json").read_text())
    assert manifest["files"][0]["url"] is None
    assert manifest["files"][0]["sheets"][0]["mapped_headers"][0] == "CASE_NUMBER"
    table = pq.read_table(tmp_path / "processed" / "main" / "fy2027_q1.parquet")
    assert table.column_names == list(schema.MAIN_COLUMNS) + list(pipeline.PROVENANCE)
    assert table.column("H_1B_DEPENDENT").to_pylist() == ["Yes"]
    assert table.column("EMPLOYER_FEIN").null_count == 1


def test_unknown_column_fails_before_conversion(tmp_path: Path) -> None:
    item = source("FY2027_Q1", "main", "new.xlsx")
    path = tmp_path / item.filename
    workbook(path, MAIN_HEADERS + ("SURPRISE_COLUMN",), [])

    with pytest.raises(ValueError, match="SURPRISE_COLUMN"):
        inspect(item, path)


def test_repeated_case_and_multiple_worksites_are_counted_separately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = tmp_path / "raw"
    output = tmp_path / "processed"
    raw.mkdir()
    sources = (
        source("FY2022_Q2", "main", "q2.xlsx"),
        source("FY2022_Q4", "main", "q4.xlsx"),
        source("FY2023_Q1", "main", "next_year.xlsx"),
        source("FY2022_Q4", "worksites", "worksites.xlsx"),
    )
    workbook(
        raw / "q2.xlsx",
        MAIN_HEADERS,
        [
            (
                "A",
                "Certified",
                "2022-02-01",
                "2022-02-03",
                None,
                "H-1B",
                "Acme",
                "15-2051",
                "New York",
                "NY",
                "10001",
            ),
            (
                "A",
                "Certified",
                "2022-02-01",
                "2022-02-03",
                None,
                "H-1B",
                "Acme",
                "15-2051",
                "New York",
                "NY",
                "10001",
            ),
            (
                "B",
                "Certified",
                "2022-03-01",
                "2022-03-02",
                None,
                "E-3",
                "Other",
                "15-2051",
                "Boston",
                "MA",
                "02101",
            ),
        ],
    )
    workbook(
        raw / "q4.xlsx",
        MAIN_HEADERS + ("EMPLOYER_FEIN", "H-1B_DEPENDENT"),
        [
            (
                "A",
                "Withdrawn",
                "2022-08-01",
                "2022-08-03",
                None,
                "H-1B",
                "Acme",
                "15-2051",
                "New York",
                "NY",
                "10001",
                "123",
                "Yes",
            ),
            (
                "C",
                "Certified",
                "2022-09-01",
                None,
                None,
                "H-1B",
                "Acme",
                "15-2051",
                "Los Angeles",
                "CA",
                "90001",
                None,
                "No",
            ),
        ],
    )
    workbook(
        raw / "next_year.xlsx",
        MAIN_HEADERS,
        [
            (
                "D",
                "Certified",
                "2022-11-01",
                "2022-11-03",
                None,
                "H-1B",
                "Later",
                "15-2051",
                "Chicago",
                "IL",
                "60601",
            ),
        ],
    )
    workbook(
        raw / "worksites.xlsx",
        WORKSITE_HEADERS,
        [
            ("A", "New York", "NEW YORK", "10001", 1),
            ("A", "San Francisco", "CALIFORNIA", "94102", 1),
            ("C", "Los Angeles", "CALIFORNIA", "90001", 1),
            ("D", "Chicago", "ILLINOIS", "60601", 1),
        ],
    )

    report = run(raw, output, sources)

    assert report["main"][0]["source_rows"] == 3
    assert report["main"][0]["duplicate_case_number_rows"] == 1
    assert report["main"][1]["h1b_missing_decision_date"] == 1
    assert report["case_numbers_in_multiple_releases"] == 1
    assert report["overlapping_releases"] == [
        {"left": "FY2022_Q2", "right": "FY2022_Q4", "shared_case_numbers": 1}
    ]
    worksites = report["worksites"][0]
    assert worksites["source_rows"] == 4
    assert worksites["cases_with_multiple_worksite_rows"] == 1
    assert worksites["worksite_rows_without_same_year_main"] == 1
    assert worksites["main_cases_with_same_year_worksite_row"] == 2
    assert worksites["same_year_main_to_worksite_match_pct"] == 66.67
    assert worksites["main_cases_with_first_worksite_location_match"] == 2
    assert worksites["first_worksite_location_match_pct"] == 100.0
    assert worksites["worksite_cases_with_main_in_other_year"] == 1
    assert report["global_case_links"]["main_cases_without_any_worksite_row"] == 1
    assert report["global_case_links"]["worksite_cases_without_any_selected_main"] == 0

    q2 = pq.read_table(output / "main" / "fy2022_q2.parquet")
    assert q2.num_rows == 3
    assert q2.column("EMPLOYER_FEIN").null_count == 3
    assert q2.column("SOURCE_RELEASE").to_pylist() == ["FY2022_Q2"] * 3
    q4 = pq.read_table(output / "main" / "fy2022_q4.parquet")
    assert q4.column("CASE_STATUS").to_pylist() == ["Withdrawn", "Certified"]
    assert q4.column("DECISION_DATE").to_pylist() == ["2022-08-03", None]
    assert q4.column("H_1B_DEPENDENT").to_pylist() == ["Yes", "No"]
    assert "H-1B_DEPENDENT" not in q4.column_names
    manifest = json.loads((output / "source_manifest.json").read_text())
    assert [item["sheets"][0]["data_rows"] for item in manifest["files"]] == [3, 2, 1, 4]
    assert manifest["files"][1]["sheets"][0]["headers"][-1] == "H-1B_DEPENDENT"
    assert "H-1B_DEPENDENT" not in manifest["processed_columns"]["main"]
    assert "local_modified_at_utc" in manifest["files"][0]

    def fail_if_converted(*args: object) -> None:
        raise AssertionError("Unchanged files were converted again")

    monkeypatch.setattr("h1b_job_insights.pipeline.inspect", fail_if_converted)
    monkeypatch.setattr("h1b_job_insights.pipeline.convert", fail_if_converted)
    assert run(raw, output, sources) == report

    monkeypatch.undo()
    new = source("FY2024_Q1", "main", "later.xlsx")
    workbook(
        raw / new.filename,
        MAIN_HEADERS,
        [
            (
                "E", "Certified", "2023-11-01", "2023-11-02", None,
                "H-1B", "New Co", "15-2051", "Boston", "MA", "02101",
            )
        ],
    )
    converted = []
    original_convert = pipeline.convert

    def track_convert(*args: object, **kwargs: object) -> int:
        converted.append(args[0].source.filename)
        return original_convert(*args, **kwargs)

    monkeypatch.setattr(pipeline, "convert", track_convert)
    updated = run(raw, output, (*sources, new))
    assert converted == ["later.xlsx"]
    assert updated["main"][-1]["source_rows"] == 1
    assert updated["main"][0] == report["main"][0]
