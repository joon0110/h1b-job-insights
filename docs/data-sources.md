# DOL LCA data

The main LCA disclosure files come from the DOL OFLC
[performance data page](https://www.dol.gov/agencies/eta/foreign-labor/performance).
Download links and filenames are in the [README](../README.md). The files include
H-1B, H-1B1, and E-3 cases. Company counts use H-1B cases only.

The selected files run from FY2022 Q1 through FY2026 Q3. FY2023 Q2 repeats
some FY2023 Q1 case numbers, and the FY2026 Q3 file covers all three quarters
of FY2026. The DOL page spells the FY2026 Q3 filename
`LCA_Dislclosure_Data_FY2026_Q3.xlsx`, while its link uses
`LCA_Disclosure_Data_FY2026_Q3.xlsx`.

The five main record layouts are in [source-layouts](source-layouts/), with
checksums in [SHA256SUMS](source-layouts/SHA256SUMS).

## File formats

| Main files | Columns | Difference |
| --- | ---: | --- |
| FY2022–FY2023 | 96 | Base layout |
| FY2024 | 97 | Adds `EMPLOYER_FEIN` |
| FY2025 Q1 | 97 | Uses `H-1B_DEPENDENT` |
| FY2025 Q2–Q4, FY2026 Q3 | 98 | Adds `LAWFIRM_BUSINESS_FEIN`; uses `H_1B_DEPENDENT` |

The pipeline maps `H-1B_DEPENDENT` to `H_1B_DEPENDENT` and writes the same
98 columns for every release. Missing optional columns are null. Original
headers remain in `data/processed/source_manifest.json`; unknown headers stop
processing.

## Counting cases

`CASE_NUMBER` can repeat across releases. Company counts keep the newest
available version of each case. `DECISION_DATE` determines its fiscal quarter,
where Q1 is October–December. `CASE_STATUS` determines whether a case is
`Certified`; the total LCA count includes every status. `TOTAL_WORKER_POSITIONS`
is summed separately as requested positions. It does not identify individual
workers or confirm hires.
