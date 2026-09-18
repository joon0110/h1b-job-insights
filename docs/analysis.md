# Company activity analysis

Run `python -m h1b_job_insights.eda` after preparing the Parquet files.
Results go to `artifacts/eda/`. The analysis uses the 17 selected releases
from FY2022 Q1 through FY2026 Q3, with each case kept at its latest version.

## Findings

| Measure | Result |
| --- | ---: |
| Employer names | 142,253 |
| Fiscal quarters | 19 |
| H-1B LCA cases | 2,629,782 |
| Requested positions | 4,546,577 |
| Companies with at least four observed quarters | 125,863 |
| Zero-case quarters in those companies' first four quarters | 61.92% |
| Companies active in exactly one of their first four quarters | 68.49% |
| Median cases per company over the full period | 2 |
| Share of cases from the largest 1% of companies | 58.13% |
| Share of requested positions from the largest 1% | 74.89% |

The two concentration figures rank companies separately by their respective
totals. The case and position totals also match an independent aggregation
from the source Parquet files for every quarter.

Companies enter at their first recorded quarter. They remain in the data through
FY2026 Q3, including inactive quarters; 72.55% of all those company-quarter rows
have zero cases. The charts show:

- Top left: companies with at least one case and positions requested in each
  quarter. FY2022 Q1 has 17,806 companies and 210,242 requested positions.
  The two lines use separate, labeled scales. Requested positions are not a
  count of distinct people or hires.
- Top right: how many of each company's first four quarters had at least one case.
  Only companies observed for four quarters are included. Their first quarter
  must have activity because it is when they first appear.
- Bottom left: of the companies with a case in the previous quarter, the share
  that had another case in the current quarter. FY2022 Q1 has no previous
  quarter, so its rate is blank.
- Bottom right: how many cases a company had in one of its first four quarters.
  The 0 bar includes quarters with no case. Each company contributes four
  quarters, so the bars count company-quarter rows rather than companies.

Among adjacent quarters, companies with current activity have activity again
45.12% of the time; those without current activity do so 11.48% of the time.
These are descriptive rates from revised history, not model predictions.
Fiscal Q3 has the most cases in every available year. High totals do not show
how many individual companies filed; the largest 1% account for 58.13% of cases.

Among companies with a fifth quarter available, the share with an LCA case in
that quarter was:

| Active quarters in first four | Companies | Active in fifth quarter |
| ---: | ---: | ---: |
| 1 | 83,992 | 10.16% |
| 2 | 21,581 | 24.67% |
| 3 | 8,858 | 45.15% |
| 4 | 8,554 | 79.34% |

These rates come from revised records and do not measure forecast accuracy.

| Minimum company history | Adjacent-quarter pairs | Share of all pairs | Next quarter active |
| --- | ---: | ---: | ---: |
| 1 quarter | 1,520,616 | 100.00% | 20.67% |
| 4 quarters | 1,136,396 | 74.73% | 21.75% |
| 8 quarters | 693,969 | 45.64% | 23.92% |

Four quarters provide one year of history while retaining roughly three quarters
of the candidate pairs. These counts describe the current data; actual training
eligibility also depends on when each source was published.

## Prediction target

The first model estimates the probability of at least one H-1B LCA record for a
company in the next fiscal quarter. A positive label means `LCA_CASES > 0`, using
`DECISION_DATE` and all statuses. This measures recorded LCA activity, including
withdrawals and denials. It does not estimate a job applicant's chance of getting
sponsored. Requested positions and case counts remain descriptive measures for
this experiment.

Use the existing employer-name grouping without FEIN, occupation, or location.
Require four covered quarters from the company's first known record. Keep later
zero quarters, but do not insert zeros before a company is known or where source
coverage is missing. Companies without enough history get no probability yet.
The last observed quarter has no next-quarter label.

## Models

Compare three classifiers on the same features and time splits:

| Model | Library | Role |
| --- | --- | --- |
| Logistic regression | scikit-learn `LogisticRegression` | Simple probability baseline |
| Random forest | scikit-learn `RandomForestClassifier` | Compare combinations of activity patterns |
| XGBoost | xgboost `XGBClassifier`, `objective="binary:logistic"` | Compare boosted decision trees |

Start with recent quarterly case counts, the number of active quarters, time
since the last activity, and the target fiscal quarter. Build these from data
available at the forecast date. Fit logistic regression's scaling on training
data only. Choose the final model using validation probability error and
calibration; XGBoost is not assumed to win. No models have been trained yet.

## Time and source versions

Across all visa classes, 169,886 rows repeat an earlier case number. Of these,
71,885 change status and decision date. Replacing old rows with their latest
version can move a case into another quarter.

For a forecast at a quarter's end, build the company list and history only from
files already public on that date. Freeze each target label using the first
release documented to cover the full target quarter. Later corrections must not
rewrite that label or enter earlier features. Training labels must also have
been published before fitting.

The source manifest has local modification times, not verified publication
dates. `source_coverage.csv` shows which decision quarters appear in each file;
their presence alone does not prove complete coverage. The FY2026 Q3 file
contains Q1 and Q2 decisions, but cannot establish what was known in Q1 or Q2.
The current analysis describes revised history. A historical forecast evaluation
requires verified release dates and the corresponding snapshots.

All latest H-1B cases have valid received and decision dates. Their median gap is
7 days, with a 99th percentile of 796 days. This includes later status decisions;
it is neither a publication delay nor a clean estimate of initial processing time.

## Evaluation

Use FY2023 target quarters for initial training and FY2024 for validation with
an expanding training window. After choosing settings, refit using labels
available before the first FY2025 test origin and keep the model fixed for the
FY2025 test. FY2022 supplies initial history. Reserve FY2026 for a later extension
once its earlier snapshots are available. All splits are by target quarter;
rows are never shuffled across time.

Compare against the training activity rate, rates by fiscal quarter, and rates
conditioned on previous activity. Fit those rates on training data only. Use
Brier score for probability error, average precision for ranking, and a
calibration plot to compare predicted percentages with observed frequencies.
Report each quarter separately and average the quarterly scores. Also compare
companies by history length and prior-year case volume, using only past data to
form those groups. Report the share of known companies eligible for a prediction.
