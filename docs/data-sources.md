# DOL LCA data

The files come from the DOL OFLC [performance data page](https://www.dol.gov/agencies/eta/foreign-labor/performance).
Download links and exact filenames are in the [README](../README.md). The raw
files include H-1B, H-1B1, and E-3 applications. Analysis starts with H-1B
decisions dated January 1, 2022 or later.

The FY2022–FY2025 Q4 main files cover July–September, so all four quarters are
needed for each of those years. FY2023 Q2 also repeats every FY2023 Q1 case
number. The FY2026 Q3 main file is cumulative through Q3. Worksites are in
separate files.

The DOL page labels the FY2026 Q3 main file
`LCA_Dislclosure_Data_FY2026_Q3.xlsx`, but its link uses
`LCA_Disclosure_Data_FY2026_Q3.xlsx`. Its worksite link uses
`LCA_Worksites_FY_2026_Q3.xlsx`. Use the linked names shown in the README.

Copies of the ten DOL record layouts are in [source-layouts](source-layouts/).
Their checksums are in [SHA256SUMS](source-layouts/SHA256SUMS).

## File formats

| Main files | Columns | Difference |
| --- | ---: | --- |
| FY2022–FY2023 | 96 | Base layout |
| FY2024 | 97 | Adds `EMPLOYER_FEIN` |
| FY2025 Q1 | 97 | Uses `H-1B_DEPENDENT` |
| FY2025 Q2–Q4, FY2026 Q3 | 98 | Adds `LAWFIRM_BUSINESS_FEIN`; uses `H_1B_DEPENDENT` |

Each worksite file has 22 columns. The pipeline maps `H-1B_DEPENDENT` to
`H_1B_DEPENDENT` and writes the same 98 main columns or 22 worksite columns
for every release. Missing optional columns are null. The original headers
remain in `data/processed/source_manifest.json`; unknown headers stop processing.

## Reading the records

`CASE_NUMBER` repeats across releases, so adding file row counts would
overcount cases. The main file contains only the first worksite; the separate
worksite file can contain multiple rows per case. Some worksite rows match a
main case from another fiscal year. The FY2026 Q3 main file also has cases
without a row in the selected worksite file. Exact counts are in
`data/processed/quality.json` after processing.

`CASE_STATUS` is the latest significant event or decision, and `DECISION_DATE`
is that event's date. `ORIGINAL_CERT_DATE` records the first certification for
`Certified-Withdrawn` cases. `TOTAL_WORKER_POSITIONS` counts requested workers,
not applications or hires. Wage amounts keep their source units, which can be
Hour, Week, Bi-Weekly, Month, or Year.
