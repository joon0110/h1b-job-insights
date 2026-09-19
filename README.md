# H-1B Job Insights

Look up a company's quarterly H-1B Labor Condition Application (LCA) counts and
estimate the probability of at least one record next quarter. Data comes from
U.S. Department of Labor disclosure files.

## Setup

Use Python 3.11 or newer. Install the dependencies listed in
[pyproject.toml](pyproject.toml):

On macOS, install Python and OpenMP first:

```sh
brew install python@3.13 libomp
python3.13 -m venv .venv
```

On other systems, check `python3 --version` is at least 3.11, then create the
environment with `python3 -m venv .venv`.

```sh
source .venv/bin/activate
python -m pip install -e '.[data,analysis,ml,dev]'
```

Run the commands below from the repository root.

## Look up a company

After preparing the data and training the models, run:

```sh
python -m h1b_job_insights.activity_predict --company "Amazon.com Services LLC"
```

XGBoost is the default. To use Random Forest:

```sh
python -m h1b_job_insights.activity_predict \
  --company "Amazon.com Services LLC" --model random_forest
```

Each command prints the company's quarterly counts, followed by:

```text
History through FY2026_Q2; target FY2026_Q3
Probability of at least one H-1B LCA record: 99.1%
```

The example uses XGBoost. Its model is in `artifacts/activity/trend_constraints/`;
Random Forest's is in `artifacts/activity/`. Each directory contains
`classifiers.joblib`. `--model-dir` overrides this location.

Companies need at least four quarters of history. The prediction is for the
quarter after the data cutoff, which may differ from the current quarter.

## Prepare the data

Download the main Excel files below into `data/raw/`, keeping these filenames.
Create the folder with `mkdir -p data/raw`. Worksite files are not needed.
See [source notes](docs/data-sources.md) for column mappings and case counting.

| Release | Main files |
| --- | --- |
| FY2022 | [Q1](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q1.xlsx) `LCA_Disclosure_Data_FY2022_Q1.xlsx`<br>[Q2](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q2.xlsx) `LCA_Disclosure_Data_FY2022_Q2.xlsx`<br>[Q3](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q3.xlsx) `LCA_Disclosure_Data_FY2022_Q3.xlsx`<br>[Q4](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q4.xlsx) `LCA_Disclosure_Data_FY2022_Q4.xlsx` |
| FY2023 | [Q1](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q1.xlsx) `LCA_Disclosure_Data_FY2023_Q1.xlsx`<br>[Q2](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q2.xlsx) `LCA_Disclosure_Data_FY2023_Q2.xlsx`<br>[Q3](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q3.xlsx) `LCA_Disclosure_Data_FY2023_Q3.xlsx`<br>[Q4](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q4.xlsx) `LCA_Disclosure_Data_FY2023_Q4.xlsx` |
| FY2024 | [Q1](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2024_Q1.xlsx) `LCA_Disclosure_Data_FY2024_Q1.xlsx`<br>[Q2](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2024_Q2.xlsx) `LCA_Disclosure_Data_FY2024_Q2.xlsx`<br>[Q3](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2024_Q3.xlsx) `LCA_Disclosure_Data_FY2024_Q3.xlsx`<br>[Q4](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2024_Q4.xlsx) `LCA_Disclosure_Data_FY2024_Q4.xlsx` |
| FY2025 | [Q1](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q1.xlsx) `LCA_Disclosure_Data_FY2025_Q1.xlsx`<br>[Q2](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q2.xlsx) `LCA_Disclosure_Data_FY2025_Q2.xlsx`<br>[Q3](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q3.xlsx) `LCA_Disclosure_Data_FY2025_Q3.xlsx`<br>[Q4](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q4.xlsx) `LCA_Disclosure_Data_FY2025_Q4.xlsx` |
| FY2026 Q3 | [Download](https://www.dol.gov/media/LCA_Disclosure_Data_FY2026_Q3.xlsx) `LCA_Disclosure_Data_FY2026_Q3.xlsx` |

Convert the Excel files to Parquet:

```sh
python -m h1b_job_insights.pipeline
```

Outputs go to `data/processed/main/`. `source_manifest.json` records source
files, checksums, headers, and row counts; `quality.json` contains data checks.
Data and generated models are excluded from Git.

The pipeline finds files named like `LCA_Disclosure_Data_FY2027_Q1.xlsx` and
maps their headers to the same columns. Missing optional columns become null.
Unknown or missing required columns stop the run with the filename and column
names. Add confirmed header changes to `src/h1b_job_insights/schema.py`.

Unchanged files are reused. Adding a file converts that file and refreshes the
combined data checks. `--force` converts everything again. All source rows,
including repeated cases, remain in the Parquet files.

## Train the models

Run this when setting up the project or rebuilding models, not for each lookup:

```sh
python -m h1b_job_insights.activity_features
python -m h1b_job_insights.activity_train --jobs 4
python -m h1b_job_insights.activity_train --constrain-trends \
  --reuse-random-forest artifacts/activity \
  --output-dir artifacts/activity/trend_constraints --jobs 4
```

The first command builds inputs in `data/processed/activity/`. The second trains
both classifiers. The third trains XGBoost with trend constraints and reuses the
saved Random Forest. Reuse requires the same data and time splits.

Features use company history, recent changes, prior activity in the same fiscal
quarter, and market totals. Names are lookup keys, not model inputs.

Model settings are selected using FY2024 outcomes. Probability calibration is
fitted on FY2025 Q1–Q2 predictions and kept only if it improves the score on
FY2025 Q3–Q4. Final training uses outcomes through FY2026 Q2. New forecast
periods require updating these splits and retraining. The current saved models
use probabilities without calibration.

For XGBoost, lower recent or annual growth, fewer active quarters, and longer
inactivity cannot raise the probability when other inputs stay fixed. Flat
responses are allowed. Seasonal and market changes can still raise a company's
next-quarter probability. Calibration is applied only if it preserves these
directions and improves the validation score.

## Historical counts and charts

To see counts, requested positions, and quarterly changes by decision date:

```sh
python -m h1b_job_insights.company_activity
python -m h1b_job_insights.company_activity --company "Amazon.com Services LLC"
```

The first command writes `data/processed/company_activity/company_quarters.parquet`.
The second reads it. `LCA_CASES` includes all statuses; `CERTIFIED_CASES` includes
only `Certified`. `REQUESTED_POSITIONS` sums `TOTAL_WORKER_POSITIONS`.

To generate the four historical charts by receipt date:

```sh
python -m h1b_job_insights.eda
```

`artifacts/eda/overview.png` shows quarterly active companies, activity in each
company's first four quarters, filing rates after active or inactive quarters,
and next-quarter record/no-record counts. The last two charts require four
quarters of prior history and an observed next quarter.

Chart counts and requested positions are in `quarters.csv` and `summary.json`.
`source_coverage.csv` shows receipt quarters by source release.
See [analysis notes](docs/analysis.md) for the results and chart definitions.

## Data definitions

- Companies are grouped by normalized name, ignoring FEIN, job title, and
  worksite. Different names stay separate, including renamed companies.
- Each case is counted once using its newest available version. Quarters after
  a company's first record receive zero when no cases appear.
- Fiscal Q1 is October–December. Predictions and charts use `RECEIVED_DATE`;
  the separate company-count command uses `DECISION_DATE`.
- Requested positions are not distinct workers or confirmed hires. Filing
  probabilities do not describe an individual's sponsorship or visa approval chance.
- The files contain revisions to past records. They do not reconstruct what was
  available at each historical forecast date. The latest source quarter is
  omitted as a buffer; earlier quarters may still be incomplete.

## Tests

Tests for data conversion, company counts, charts, and models are in `tests/`.
With the setup dependencies installed, run:

```sh
python -m pytest tests
```

To compare predictions with actual FY2026 Q1–Q2 records:

```sh
python -m tests.check_models --jobs 4
```

This fits temporary classifiers using the saved settings and outcomes through
FY2025 Q4. Both target quarters use that same cutoff. It writes predictions,
error metrics, and filing rates by probability band to `artifacts/checks/models/`.
The saved models used for company lookups are unchanged. The records include
later revisions, and this period has already been used in earlier experiments.

To check the saved XGBoost's trend constraints:

```sh
python -m tests.check_constraints
```

This changes one input at a time on up to 512 sampled rows and checks whether
the probability follows the specified direction. It does not measure accuracy.
The Excel pipeline and EDA commands also retain their source-data checks.
