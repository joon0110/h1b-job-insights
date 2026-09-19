# Company activity analysis

Run `python -m h1b_job_insights.eda` after preparing the Parquet files.
Results go to `artifacts/eda/`.

The analysis uses receipt dates (`RECEIVED_DATE`) from FY2022 Q1 through
FY2026 Q3. Each case is kept at its latest version across the 17 selected
releases, including the latest source quarter. Later releases may revise these
counts. The figures below describe this run; rerun EDA after adding a release.

## Findings

| Measure | Result |
| --- | ---: |
| Employer names | 140,609 |
| Fiscal quarters | 19 |
| H-1B LCA cases | 2,582,867 |
| Requested positions | 4,480,947 |
| Companies with at least four observed quarters | 124,796 |
| Companies active in exactly one of their first four quarters | 69.03% |
| Eligible next-quarter pairs | 1,130,529 |
| Pairs with no next-quarter record | 888,938 (78.63%) |
| Pairs with at least one next-quarter record | 241,591 (21.37%) |

A company enters the panel at its first filing within the analysis window.
Quarters with no record after that point receive zero cases. The panel does not
include companies that never appear in these files. Cases include all statuses.
Company names are normalized; FEIN does not affect grouping.

## Reading the charts

1. **Companies filing each quarter.** Each company counts once in a quarter,
   whether it filed one LCA or hundreds. FY2022 Q1 has 17,226 companies.
   Requested positions are in the CSV and summary.
2. **Activity in the first four observed quarters.** Of 124,796 companies with
   four quarters available, 86,146 filed in just one of those quarters. The four
   quarters start at each company's first observed filing, so their dates differ
   across companies. The first quarter always has a filing; there is no zero bar.
3. **Filing after an active or inactive quarter.** The two lines separate companies
   that filed in the previous quarter from those that did not. Each line shows
   the percentage of its own group that filed in the outcome quarter on the
   x-axis. For FY2023 Q1, these rates are 70.92% and 16.89%.
4. **Next-quarter outcomes.** Each observation pairs a company's history with
   its following quarter. The bars count no record versus at least one record.
   For example, a company's Q4 history and Q1 outcome form one pair; its Q1
   history and Q2 outcome form another. The same company can contribute several
   pairs. These are historical outcomes, not predicted probabilities.

Charts 3 and 4 use the same 1,130,529 pairs from 122,220 companies. Each pair
requires at least four quarters of prior history and an observed adjacent next
quarter. The final quarter cannot supply a pair with an unknown future outcome.
The first possible outcome is FY2023 Q1, after four quarters of FY2022 history.
These counts cover the full analysis period, before any train/test split.

## Checks and limits

Quarterly case and requested-position totals match an independent aggregation
from the source Parquet files.

Across all visa classes, 169,886 rows repeat an earlier case number. Of these,
71,885 change status and decision date; none change receipt date. The source
files contain revised history, and their original publication dates have not
been verified. This analysis does not reconstruct what was known at a past
forecast date.

`quarters.csv` contains the chart counts and rate denominators. `summary.json`
contains the distributions, source checksums, and date checks.
`source_coverage.csv` audits all selected source rows by release and receipt
quarter, including rows outside the chart window. It retains duplicate versions.

The separate company-count command still uses decision dates. Its quarterly
numbers will differ from these receipt-date charts. Requested positions are
positions listed on LCAs, not distinct people or hires.
