# H-1B Job Insights

Look up a company's quarterly H-1B Labor Condition Application (LCA) counts and
estimate the probability of at least one record next quarter. Data comes from
U.S. Department of Labor disclosure files.

## Tools

- Python 3.11+ with openpyxl for Excel files, PyArrow for Parquet, and pandas
  and NumPy for data preparation.
- SQL with SQLite to deduplicate cases and count company activity by quarter.
  The database is temporary; processed data is saved as Parquet.
- scikit-learn and XGBoost for models, joblib for saving them, and Matplotlib
  for charts. pytest and Ruff are used for checks.

## Fiscal quarters

DOL files use the U.S. government fiscal year (FY). It begins in October and
ends the following September. The FY number is the calendar year in which it
ends, so Q1 falls in the previous calendar year.

| FY quarter | Months |
| --- | --- |
| Q1 | October–December |
| Q2 | January–March |
| Q3 | April–June |
| Q4 | July–September |

## 1. Install

Use Python 3.11 or newer. Clone the repo and enter its directory:

```sh
git clone https://github.com/joon0110/h1b-job-insights.git
cd h1b-job-insights
```

On macOS, install Python and OpenMP, then create a virtual environment:

```sh
brew install python@3.13 libomp
python3.13 -m venv .venv
```

On Linux, use `python3 -m venv .venv` with Python 3.11 or newer. Activate the
environment and install the dependencies from [pyproject.toml](pyproject.toml):

```sh
source .venv/bin/activate
python -m pip install -e '.[data,analysis,ml,dev]'
```

Run the remaining commands from the repository root with this environment active.

## 2. Add the Excel files

Create the input folder, then download the main Excel files below into it. Keep
the filenames shown in the table. The repo does not download the files for you.
Worksite files are not needed.

```sh
mkdir -p data/raw
```

| Release | Main files |
| --- | --- |
| FY2022 | [Q1](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q1.xlsx) `LCA_Disclosure_Data_FY2022_Q1.xlsx`<br>[Q2](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q2.xlsx) `LCA_Disclosure_Data_FY2022_Q2.xlsx`<br>[Q3](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q3.xlsx) `LCA_Disclosure_Data_FY2022_Q3.xlsx`<br>[Q4](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q4.xlsx) `LCA_Disclosure_Data_FY2022_Q4.xlsx` |
| FY2023 | [Q1](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q1.xlsx) `LCA_Disclosure_Data_FY2023_Q1.xlsx`<br>[Q2](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q2.xlsx) `LCA_Disclosure_Data_FY2023_Q2.xlsx`<br>[Q3](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q3.xlsx) `LCA_Disclosure_Data_FY2023_Q3.xlsx`<br>[Q4](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q4.xlsx) `LCA_Disclosure_Data_FY2023_Q4.xlsx` |
| FY2024 | [Q1](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2024_Q1.xlsx) `LCA_Disclosure_Data_FY2024_Q1.xlsx`<br>[Q2](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2024_Q2.xlsx) `LCA_Disclosure_Data_FY2024_Q2.xlsx`<br>[Q3](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2024_Q3.xlsx) `LCA_Disclosure_Data_FY2024_Q3.xlsx`<br>[Q4](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2024_Q4.xlsx) `LCA_Disclosure_Data_FY2024_Q4.xlsx` |
| FY2025 | [Q1](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q1.xlsx) `LCA_Disclosure_Data_FY2025_Q1.xlsx`<br>[Q2](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q2.xlsx) `LCA_Disclosure_Data_FY2025_Q2.xlsx`<br>[Q3](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q3.xlsx) `LCA_Disclosure_Data_FY2025_Q3.xlsx`<br>[Q4](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q4.xlsx) `LCA_Disclosure_Data_FY2025_Q4.xlsx` |
| FY2026 Q3 | [Download](https://www.dol.gov/media/LCA_Disclosure_Data_FY2026_Q3.xlsx) `LCA_Disclosure_Data_FY2026_Q3.xlsx` |

As of September 2026, DOL's [disclosure page](https://www.dol.gov/agencies/eta/foreign-labor/performance)
lists only the FY2026 Q3 main LCA file.

## 3. Convert and train

```sh
python -m h1b_job_insights.refresh
```

This command reads `data/raw/`, converts new or changed Excel files to Parquet,
builds company histories, and trains Random Forest and XGBoost. The XGBoost model
uses the trend constraints described below. Existing converted files are reused;
model training runs each time. The first run can take over 15 minutes because the
Excel files are large.

Converted data goes to `data/processed/`; both trained models go to
`artifacts/activity/classifiers.joblib`. Data and model files are excluded from Git.

Training uses four CPU workers by default. To specify that number explicitly, run
`python -m h1b_job_insights.refresh --jobs 4`. Change `4` to use a different number.

If a required column is missing or a header is unknown, conversion stops and
names the file and column. Check the source before adding a mapping to
`src/h1b_job_insights/schema.py`. See [source notes](docs/data-sources.md) for the
existing mappings.

## 4. Look up a company

XGBoost is the default model:

```sh
python -m h1b_job_insights.activity_predict --company "Amazon.com Services LLC"
```

To use Random Forest:

```sh
python -m h1b_job_insights.activity_predict --company "Amazon.com Services LLC" --model random_forest
```

The output shows the company's quarterly counts and the probability of at least
one LCA record in the quarter after the latest source file. For example:

```text
History through FY2026_Q3; target FY2026_Q4
Probability of at least one H-1B LCA record: 99.5%
```

A company needs at least four quarters of history for a prediction. The estimate
can change when new data is added and the models are retrained.

## When a new quarter is released

Keep the existing files in `data/raw/` and add the new main Excel file with its
original name. Then run `python -m h1b_job_insights.refresh` again. Adding a file
alone does not start training.

For example, adding `LCA_Disclosure_Data_FY2026_Q4.xlsx` after its release will
train through FY2026 Q4 (July–September 2026) and forecast FY2027 Q1
(October–December 2026).

## Other commands

These commands are optional. Run them after setup; commands that read converted
data also need step 3 first.

| Command | What it does |
| --- | --- |
| `python -m h1b_job_insights.pipeline` | Convert Excel files without training. |
| `python -m h1b_job_insights.pipeline --force` | Reconvert all Excel files, including unchanged ones. |
| `python -m h1b_job_insights.activity_features` | Rebuild company history and model inputs after conversion. |
| `python -m h1b_job_insights.activity_train` | Train both models from the prepared inputs. |
| `python -m h1b_job_insights.company_activity` | Build company counts and requested positions by decision date. |
| `python -m h1b_job_insights.company_activity --company "Amazon.com Services LLC"` | Show one company's decision-date counts and changes. Run the command above first. |
| `python -m h1b_job_insights.eda` | Generate historical charts and CSV summaries in `artifacts/eda/`. See [analysis notes](docs/analysis.md). |
| `python -m pytest tests` | Run the automated tests. |
| `python -m tests.check_models` | Compare predictions with the last two known quarters. Writes optional results to `artifacts/checks/models/`. |
| `python -m tests.check_constraints` | Check the saved XGBoost model's trend directions. |
| `python -m ruff check .` | Check Python code style. |

`tests.check_models` retrains temporary models using only data before its two
target quarters. With data through FY2026 Q3, it uses FY2026 Q1 as the cutoff and
compares predictions for Q2 and Q3 with their records. Its output files are
excluded from Git and are not needed for company lookups.

## Data and model notes

- Companies are grouped by normalized name; FEIN, job title, and worksite do not
  affect grouping. Different names stay separate.
- Each case is counted once using its newest available version. The models and
  charts use `RECEIVED_DATE`; `company_activity` uses `DECISION_DATE`.
- `LCA_CASES` includes every status. `CERTIFIED_CASES` counts only `Certified`;
  `REQUESTED_POSITIONS` sums `TOTAL_WORKER_POSITIONS`.
- Model inputs include the company's past counts, recent changes, activity in the
  same fiscal quarter, and overall filing activity. Training needs at least 15
  quarters of data. XGBoost constrains selected trend features so a drop in those
  values cannot raise the probability when other inputs stay fixed.
- The probability describes at least one LCA record under that company name. It
  does not measure an individual's sponsorship or visa approval chance. Requested
  positions are not distinct workers or confirmed hires.
- FY2026 Q3 receipt counts are provisional. The Q3 file covers cases decided
  through June 30, 2026, so Q3 applications decided later are not in it. This
  is a source timing limit, not a code error.
- Later releases can revise past records. Historical checks use these revised
  records, not snapshots of what was available at each earlier forecast date.
