# H-1B Job Insights

This repo processes U.S. Department of Labor LCA disclosure files to show
historical H-1B activity by employer. An LCA is an application, not proof of a
visa approval, a hire, or future sponsorship.

## Development setup

Use Python 3.11 or newer. [pyproject.toml](pyproject.toml) defines the package
and its optional dependencies. Install the data tools and development tools with:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[data,dev]'
```

For the package alone, run `python -m pip install .`.

## Prepare the data

Download the main LCA Excel files you need and put them in `data/raw/` with the
filenames below. Create the folder if needed: `mkdir -p data/raw`. Download all
listed files for the available 2022–2026 history. Worksite files are not needed
for company counts. See [DOL source notes](docs/data-sources.md) for format details.

| Release | Main files |
| --- | --- |
| FY2022 | [Q1](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q1.xlsx) `LCA_Disclosure_Data_FY2022_Q1.xlsx`<br>[Q2](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q2.xlsx) `LCA_Disclosure_Data_FY2022_Q2.xlsx`<br>[Q3](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q3.xlsx) `LCA_Disclosure_Data_FY2022_Q3.xlsx`<br>[Q4](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q4.xlsx) `LCA_Disclosure_Data_FY2022_Q4.xlsx` |
| FY2023 | [Q1](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q1.xlsx) `LCA_Disclosure_Data_FY2023_Q1.xlsx`<br>[Q2](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q2.xlsx) `LCA_Disclosure_Data_FY2023_Q2.xlsx`<br>[Q3](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q3.xlsx) `LCA_Disclosure_Data_FY2023_Q3.xlsx`<br>[Q4](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q4.xlsx) `LCA_Disclosure_Data_FY2023_Q4.xlsx` |
| FY2024 | [Q1](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2024_Q1.xlsx) `LCA_Disclosure_Data_FY2024_Q1.xlsx`<br>[Q2](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2024_Q2.xlsx) `LCA_Disclosure_Data_FY2024_Q2.xlsx`<br>[Q3](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2024_Q3.xlsx) `LCA_Disclosure_Data_FY2024_Q3.xlsx`<br>[Q4](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2024_Q4.xlsx) `LCA_Disclosure_Data_FY2024_Q4.xlsx` |
| FY2025 | [Q1](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q1.xlsx) `LCA_Disclosure_Data_FY2025_Q1.xlsx`<br>[Q2](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q2.xlsx) `LCA_Disclosure_Data_FY2025_Q2.xlsx`<br>[Q3](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q3.xlsx) `LCA_Disclosure_Data_FY2025_Q3.xlsx`<br>[Q4](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q4.xlsx) `LCA_Disclosure_Data_FY2025_Q4.xlsx` |
| FY2026 Q3 | [Download](https://www.dol.gov/media/LCA_Disclosure_Data_FY2026_Q3.xlsx) `LCA_Disclosure_Data_FY2026_Q3.xlsx` |

From the repository root, run:

```sh
python -m h1b_job_insights.pipeline
```

The command finds the main workbooks in `data/raw/`, validates their headers, and
writes Parquet files to `data/processed/main/`.
`data/processed/source_manifest.json` records file checksums, headers, and row
counts. `data/processed/quality.json` contains the validation results. The raw
and processed data folders are ignored by Git.

New quarterly files are picked up when named like
`LCA_Disclosure_Data_FY2027_Q1.xlsx`. The pipeline maps their headers into a
fixed set of columns; missing optional columns become null. Unknown columns or
missing required columns stop processing with the filename and column names.
Add confirmed header changes to `src/h1b_job_insights/schema.py` before rerunning.

The first conversion reads every workbook and can take a while. With unchanged
files, a second run reuses the output. When you add a file, the pipeline converts
that file and rechecks the combined data from existing Parquet files. Use
`--force` to rebuild everything. The Parquet files keep all source rows,
including repeated cases.

## Company counts

After the Excel pipeline finishes, run:

```sh
python -m h1b_job_insights.company_activity
python -m h1b_job_insights.company_activity --company "Amazon.com Services LLC"
```

The first command writes `data/processed/company_activity/company_quarters.parquet`.
The second prints one company's quarterly counts and changes. Names are grouped
after normalizing capitalization, spaces, and punctuation in endings such as
`LLC`. FEIN, job title, and worksite do not affect the grouping. Different names
are kept separate.

Each case number is counted once using its latest available release. `LCA_CASES`
includes all statuses; `CERTIFIED_CASES` counts only `Certified`. Quarters follow
the U.S. federal fiscal year: Q1 is October–December. Missing quarters after a
company's first record appear as zero. Change percentage is blank when the
previous quarter had zero cases. These figures describe LCA decisions, not visa
approvals or hires. After adding a file, rerun the Excel pipeline and company
counts. Data files are ignored by Git.
