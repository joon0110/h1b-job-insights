# H-1B Job Insights

This repo processes U.S. Department of Labor LCA disclosure files for H-1B
company, role, and worksite analysis. An LCA is an application, not a visa
approval or a record of a hire.

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

Download the Excel files you need and put them directly in `data/raw/` with the
linked filenames. Create the folder if needed: `mkdir -p data/raw`. Download
all listed files for the full 2022–2026 history. These are `.xlsx` workbooks,
not CSV files. The FY2026 worksite filename includes an extra underscore before
`2026`. The files are also listed by release in the
[DOL source review](docs/data-sources.md).

| Release | Main files | Worksite file |
| --- | --- | --- |
| FY2022 | [Q1](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q1.xlsx) `LCA_Disclosure_Data_FY2022_Q1.xlsx`<br>[Q2](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q2.xlsx) `LCA_Disclosure_Data_FY2022_Q2.xlsx`<br>[Q3](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q3.xlsx) `LCA_Disclosure_Data_FY2022_Q3.xlsx`<br>[Q4](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q4.xlsx) `LCA_Disclosure_Data_FY2022_Q4.xlsx` | [Download](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Worksites_FY2022_Q4.xlsx) `LCA_Worksites_FY2022_Q4.xlsx` |
| FY2023 | [Q1](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q1.xlsx) `LCA_Disclosure_Data_FY2023_Q1.xlsx`<br>[Q2](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q2.xlsx) `LCA_Disclosure_Data_FY2023_Q2.xlsx`<br>[Q3](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q3.xlsx) `LCA_Disclosure_Data_FY2023_Q3.xlsx`<br>[Q4](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q4.xlsx) `LCA_Disclosure_Data_FY2023_Q4.xlsx` | [Download](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Worksites_FY2023_Q4.xlsx) `LCA_Worksites_FY2023_Q4.xlsx` |
| FY2024 | [Q1](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2024_Q1.xlsx) `LCA_Disclosure_Data_FY2024_Q1.xlsx`<br>[Q2](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2024_Q2.xlsx) `LCA_Disclosure_Data_FY2024_Q2.xlsx`<br>[Q3](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2024_Q3.xlsx) `LCA_Disclosure_Data_FY2024_Q3.xlsx`<br>[Q4](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2024_Q4.xlsx) `LCA_Disclosure_Data_FY2024_Q4.xlsx` | [Download](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Worksites_FY2024_Q4.xlsx) `LCA_Worksites_FY2024_Q4.xlsx` |
| FY2025 | [Q1](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q1.xlsx) `LCA_Disclosure_Data_FY2025_Q1.xlsx`<br>[Q2](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q2.xlsx) `LCA_Disclosure_Data_FY2025_Q2.xlsx`<br>[Q3](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q3.xlsx) `LCA_Disclosure_Data_FY2025_Q3.xlsx`<br>[Q4](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q4.xlsx) `LCA_Disclosure_Data_FY2025_Q4.xlsx` | [Download](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Worksites_FY2025_Q4.xlsx) `LCA_Worksites_FY2025_Q4.xlsx` |
| FY2026 Q3 | [Download](https://www.dol.gov/media/LCA_Disclosure_Data_FY2026_Q3.xlsx) `LCA_Disclosure_Data_FY2026_Q3.xlsx` | [Download](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/FY26Q3/LCA_Worksites_FY_2026_Q3.xlsx) `LCA_Worksites_FY_2026_Q3.xlsx` |

From the repository root, run:

```sh
python -m h1b_job_insights.pipeline
```

The command finds the workbooks in `data/raw/`, validates their headers, and
writes Parquet files to `data/processed/main/` and `data/processed/worksites/`.
`data/processed/source_manifest.json` records file checksums, headers, and row
counts. `data/processed/quality.json` contains the validation results. The raw
and processed data folders are ignored by Git.

New quarterly files are picked up when named like
`LCA_Disclosure_Data_FY2027_Q1.xlsx` or `LCA_Worksites_FY2027_Q4.xlsx`. The
pipeline maps their headers into a fixed set of main and worksite columns;
missing optional columns become null. Unknown columns or missing required
columns stop processing with the filename and column names. Add a confirmed name
change to `src/h1b_job_insights/schema.py` before rerunning.

The first conversion reads every workbook and can take a while. With unchanged
files, a second run reuses the output. When you add a file, the pipeline converts
that file and rechecks the combined data from existing Parquet files. Use
`--force` to rebuild everything. The Parquet files keep all source rows,
including repeated cases; select H-1B records from January 2022 onward when
analyzing them. Do not add release row counts together as unique cases.
