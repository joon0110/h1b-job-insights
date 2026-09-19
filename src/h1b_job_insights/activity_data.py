import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd

from h1b_job_insights import company_activity, normalize


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def quarter_number(label: str) -> int:
    return int(label[2:6]) * 4 + int(label[-1]) - 1


def prepare_panel(processed_dir: Path, output_dir: Path) -> dict:
    source = json.loads((processed_dir / "source_manifest.json").read_text())
    files = sorted((x for x in source["files"] if x["kind"] == "main"), key=lambda x: x["release"])
    if not files:
        raise ValueError("No main files in source manifest")
    first = quarter_number(files[0]["release"])
    last_release = quarter_number(files[-1]["release"])
    last = last_release - 1
    if last - first < 4:
        raise ValueError("Need at least five retained quarters for next-quarter activity analysis")
    version = {
        "sources": [[item["release"], item["sha256"]] for item in files],
        "code": sha256(Path(__file__)),
        "aggregation_code": sha256(Path(company_activity.__file__)),
        "normalization_code": sha256(Path(normalize.__file__)),
        "first": first,
        "last": last,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    cache = output_dir / "panel_manifest.json"
    panel_path = output_dir / "company_quarters.parquet"
    if cache.exists() and panel_path.exists():
        saved = json.loads(cache.read_text())
        if saved["version"] == version and saved["panel_sha256"] == sha256(panel_path):
            return saved
    with tempfile.TemporaryDirectory(prefix="receipt-cases-", dir=output_dir) as temp:
        db = sqlite3.connect(Path(temp) / "cases.sqlite")
        db.execute("PRAGMA journal_mode=OFF")
        db.execute("PRAGMA synchronous=OFF")
        db.execute(
            "CREATE TABLE cases (case_number TEXT PRIMARY KEY, visa_class TEXT, "
            "employer_name TEXT, employer_id TEXT, status TEXT, quarter INTEGER, positions INTEGER)"
        )
        rows = missing = 0
        for item in files:
            print(f"Read receipt dates: {item['release']}", flush=True)
            path = processed_dir / "main" / f"{item['release'].lower()}.parquet"
            count, absent = company_activity.load_cases(db, path, date_column="RECEIVED_DATE")
            if count != item["sheets"][0]["data_rows"]:
                raise ValueError(f"Source row count differs: {path}")
            rows += count
            missing += absent
        invalid = db.execute(
            "SELECT COUNT(*) FROM cases WHERE visa_class='H-1B' "
            "AND (quarter IS NULL OR employer_id IS NULL)"
        ).fetchone()[0]
        if missing or invalid:
            raise ValueError(
                f"Missing case numbers: {missing}; H-1B rows without company/date: {invalid}"
            )
        excluded = db.execute(
            "SELECT COUNT(*) FROM cases WHERE visa_class='H-1B' AND (quarter < ? OR quarter > ?)",
            (first, last),
        ).fetchone()[0]
        db.execute("DELETE FROM cases WHERE quarter < ? OR quarter > ?", (first, last))
        totals = dict(
            db.execute(
                "SELECT quarter, COUNT(*) FROM cases WHERE visa_class='H-1B' GROUP BY quarter"
            )
        )
        if set(totals) != set(range(first, last + 1)):
            raise ValueError("Receipt history has an empty quarter; check source coverage")
        db.execute("CREATE INDEX cases_by_company ON cases (employer_id, quarter)")
        output_rows, companies, latest = company_activity.write_quarters(db, panel_path)
        db.close()
    frame = pd.read_parquet(panel_path, columns=["FISCAL_QUARTER", "LCA_CASES"])
    actual = frame.groupby("FISCAL_QUARTER").LCA_CASES.sum().to_dict()
    expected = {company_activity.quarter_label(q): n for q, n in totals.items()}
    if actual != expected:
        raise ValueError("Company receipt counts do not match deduplicated source counts")
    saved = {
        "version": version,
        "date_column": "RECEIVED_DATE",
        "first_quarter": company_activity.quarter_label(first),
        "last_quarter": latest,
        "latest_source_release": files[-1]["release"],
        "excluded_latest_quarters": 1,
        "excluded_h1b_cases_outside_window": excluded,
        "maturity_note": (
            "One trailing quarter omitted to reduce incomplete receipt counts; "
            "completeness is not guaranteed."
        ),
        "source_rows": rows,
        "companies": companies,
        "panel_rows": output_rows,
        "quarter_cases": expected,
        "panel_sha256": sha256(panel_path),
    }
    cache.write_text(json.dumps(saved, indent=2) + "\n")
    return saved
