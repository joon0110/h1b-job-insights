import argparse
import hashlib
import json
import sqlite3
import tempfile
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from h1b_job_insights import normalize

BATCH_SIZE = 20_000
INPUT_COLUMNS = ("CASE_NUMBER", "CASE_STATUS", "VISA_CLASS", "DECISION_DATE", "EMPLOYER_NAME")
OUTPUT_SCHEMA = pa.schema(
    [
        ("EMPLOYER_ID", pa.string()),
        ("EMPLOYER_NAME", pa.string()),
        ("FISCAL_QUARTER", pa.string()),
        ("LCA_CASES", pa.int64()),
        ("CERTIFIED_CASES", pa.int64()),
        ("CHANGE_FROM_PREVIOUS_QUARTER", pa.int64()),
        ("CHANGE_PERCENT", pa.float64()),
    ]
)


def quarter_index(value: str | None) -> int | None:
    if not value:
        return None
    try:
        day = date.fromisoformat(value[:10])
    except ValueError:
        return None
    fiscal_year = day.year + (day.month >= 10)
    fiscal_quarter = ((day.month - 10) % 12) // 3 + 1
    return fiscal_year * 4 + fiscal_quarter - 1


def quarter_label(index: int) -> str:
    return f"FY{index // 4}_Q{index % 4 + 1}"


def fingerprint(files: list[dict]) -> str:
    source_versions = [(item["release"], item["sha256"]) for item in files]
    digest = hashlib.sha256(json.dumps(source_versions).encode())
    digest.update(Path(__file__).read_bytes())
    digest.update(Path(normalize.__file__).read_bytes())
    return digest.hexdigest()


def load_cases(db: sqlite3.Connection, path: Path) -> tuple[int, int]:
    rows = 0
    missing_case_numbers = 0
    for batch in pq.ParquetFile(path).iter_batches(columns=INPUT_COLUMNS, batch_size=BATCH_SIZE):
        pending = []
        for case_number, status, visa, decision_date, raw_name in zip(
            *(batch.column(i).to_pylist() for i in range(len(INPUT_COLUMNS)))
        ):
            rows += 1
            if not case_number or not case_number.strip():
                missing_case_numbers += 1
                continue
            name = normalize.employer_name(raw_name)
            pending.append(
                (
                    case_number.strip().upper(),
                    visa.strip().upper() if visa else None,
                    name,
                    normalize.employer_id(name) if name else None,
                    status.strip() if status else None,
                    quarter_index(decision_date),
                )
            )
        db.executemany("INSERT OR REPLACE INTO cases VALUES (?, ?, ?, ?, ?, ?)", pending)
    return rows, missing_case_numbers


def write_quarters(db: sqlite3.Connection, path: Path) -> tuple[int, int, str | None]:
    bounds = db.execute(
        "SELECT MIN(quarter), MAX(quarter) FROM cases "
        "WHERE visa_class = 'H-1B' AND employer_id IS NOT NULL AND quarter IS NOT NULL"
    ).fetchone()
    first_quarter, last_quarter = bounds
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".parquet.part")
    row_count = company_count = 0
    buffer = {field.name: [] for field in OUTPUT_SCHEMA}

    def add_row(
        name_id: str, name: str, quarter: int, count: int, certified: int, previous: int
    ) -> None:
        nonlocal row_count
        values = (
            name_id,
            name,
            quarter_label(quarter),
            count,
            certified,
            None if quarter == first_quarter else count - previous,
            None
            if quarter == first_quarter or previous == 0
            else round(100 * (count - previous) / previous, 2),
        )
        for field, value in zip(OUTPUT_SCHEMA, values):
            buffer[field.name].append(value)
        row_count += 1

    try:
        with pq.ParquetWriter(partial, OUTPUT_SCHEMA, compression="zstd") as writer:
            current_id = current_name = None
            counts = {}

            def flush_company() -> None:
                nonlocal company_count
                if current_id is None:
                    return
                company_count += 1
                previous = 0
                for quarter in range(min(counts), last_quarter + 1):
                    count, certified = counts.get(quarter, (0, 0))
                    add_row(current_id, current_name, quarter, count, certified, previous)
                    previous = count
                    if len(buffer["EMPLOYER_ID"]) >= BATCH_SIZE:
                        writer.write_table(pa.Table.from_pydict(buffer, schema=OUTPUT_SCHEMA))
                        for values in buffer.values():
                            values.clear()

            query = (
                "SELECT employer_id, employer_name, quarter, COUNT(*), "
                "SUM(CASE WHEN status = 'Certified' THEN 1 ELSE 0 END) "
                "FROM cases WHERE visa_class = 'H-1B' AND employer_id IS NOT NULL "
                "AND quarter IS NOT NULL GROUP BY employer_id, employer_name, quarter "
                "ORDER BY employer_id, quarter"
            )
            for name_id, name, quarter, count, certified in db.execute(query):
                if name_id != current_id:
                    flush_company()
                    current_id, current_name, counts = name_id, name, {}
                counts[quarter] = (count, certified)
            flush_company()
            if buffer["EMPLOYER_ID"]:
                writer.write_table(pa.Table.from_pydict(buffer, schema=OUTPUT_SCHEMA))
        partial.replace(path)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return row_count, company_count, quarter_label(last_quarter) if last_quarter else None


def run(processed_dir: Path, output_dir: Path | None = None) -> dict:
    manifest = json.loads((processed_dir / "source_manifest.json").read_text())
    files = sorted(
        (item for item in manifest["files"] if item["kind"] == "main"),
        key=lambda item: item["release"],
    )
    if not files:
        raise ValueError("No main LCA files in the source manifest")
    output_dir = output_dir or processed_dir / "company_activity"
    output_dir.mkdir(parents=True, exist_ok=True)
    version = fingerprint(files)
    output_manifest = output_dir / "manifest.json"
    result_path = output_dir / "company_quarters.parquet"
    quality_path = output_dir / "quality.json"
    if output_manifest.is_file() and result_path.is_file() and quality_path.is_file():
        saved = json.loads(output_manifest.read_text())
        if saved.get("fingerprint") == version:
            print("Source files and rules unchanged; using existing company counts")
            return json.loads(quality_path.read_text())

    with tempfile.TemporaryDirectory(prefix="company-cases-", dir=output_dir) as temp:
        db = sqlite3.connect(Path(temp) / "cases.sqlite")
        db.execute("PRAGMA journal_mode=OFF")
        db.execute("PRAGMA synchronous=OFF")
        db.execute(
            "CREATE TABLE cases (case_number TEXT PRIMARY KEY, visa_class TEXT, "
            "employer_name TEXT, employer_id TEXT, status TEXT, quarter INTEGER)"
        )
        source_rows = missing_case_numbers = 0
        for item in files:
            path = processed_dir / "main" / f"{item['release'].lower()}.parquet"
            print(f"Counting {item['release']}", flush=True)
            rows, missing = load_cases(db, path)
            if rows != item["sheets"][0]["data_rows"]:
                raise ValueError(f"Row count changed in {path}: {rows}")
            source_rows += rows
            missing_case_numbers += missing
        unique_cases = db.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
        h1b_cases = db.execute("SELECT COUNT(*) FROM cases WHERE visa_class = 'H-1B'").fetchone()[0]
        counted_cases = db.execute(
            "SELECT COUNT(*) FROM cases WHERE visa_class = 'H-1B' "
            "AND employer_id IS NOT NULL AND quarter IS NOT NULL"
        ).fetchone()[0]
        db.execute("CREATE INDEX cases_by_company ON cases (employer_id, quarter)")
        output_rows, companies, latest_quarter = write_quarters(db, result_path)
        db.close()

    quality = {
        "source_rows": source_rows,
        "unique_cases": unique_cases,
        "repeated_case_rows": source_rows - missing_case_numbers - unique_cases,
        "missing_case_numbers": missing_case_numbers,
        "h1b_cases": h1b_cases,
        "h1b_cases_with_company_and_date": counted_cases,
        "companies": companies,
        "company_quarter_rows": output_rows,
        "latest_quarter": latest_quarter,
    }
    quality_path.write_text(json.dumps(quality, indent=2) + "\n")
    output_manifest.write_text(json.dumps({"fingerprint": version}, indent=2) + "\n")
    return quality


def show_company(path: Path, company: str) -> None:
    name = normalize.employer_name(company)
    if not name:
        raise ValueError("Company name is empty")
    table = pq.read_table(path, filters=[("EMPLOYER_ID", "=", normalize.employer_id(name))])
    if table.num_rows == 0:
        print(f"No H-1B LCA records found for {name}")
        return
    print(f"{name}\nQuarter      LCA cases  Certified  Change  Change %")
    for row in table.to_pylist():
        change = row["CHANGE_FROM_PREVIOUS_QUARTER"]
        percent = row["CHANGE_PERCENT"]
        print(
            f"{row['FISCAL_QUARTER']:<12} {row['LCA_CASES']:>9}  "
            f"{row['CERTIFIED_CASES']:>9}  "
            f"{change if change is not None else '-':>6}  "
            f"{f'{percent:+.2f}%' if percent is not None else '-':>8}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Count H-1B LCA cases by employer name")
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--company", help="Show the quarterly counts for one company")
    args = parser.parse_args()
    output_dir = args.processed_dir / "company_activity"
    quality = run(args.processed_dir, output_dir)
    if args.company:
        show_company(output_dir / "company_quarters.parquet", args.company)
    else:
        print(f"{quality['companies']:,} company names; results in {output_dir}")


if __name__ == "__main__":
    main()
