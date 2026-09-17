# DOL LCA source review

Reviewed September 17, 2026. The source is the U.S. Department of Labor Office of
Foreign Labor Certification (OFLC) [performance data page](https://www.dol.gov/agencies/eta/foreign-labor/performance).
Its LCA files cover H-1B, H-1B1, and E-3. The project will select H-1B records
only. The planned analysis begins January 1, 2022, so FY2022 still needs a date
filter: its disclosure starts October 1, 2021.

These are the five cumulative releases selected for the initial analysis. The
publication dates come from [OFLC announcements](https://www.dol.gov/agencies/eta/foreign-labor/news).
The decision windows and file links come from the disclosure page and record
layouts. An announcement date is a release-level availability date, not proof
that every record in a later snapshot existed in that form on that day.

| Release | Decisions covered | Announced | Main file | Worksite file | Record layouts |
| --- | --- | --- | --- | --- | --- |
| FY2022 Q4 | 2021-10-01 to 2022-09-30 | 2022-11-15 | [Main](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q4.xlsx) | [Worksites](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Worksites_FY2022_Q4.xlsx) | [Main](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Record_Layout_FY2022_Q4.pdf), [worksites](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Worksite_Record_Layout_FY2022_Q4.pdf) |
| FY2023 Q4 | 2022-10-01 to 2023-09-30 | 2023-11-15 | [Main](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q4.xlsx) | [Worksites](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Worksites_FY2023_Q4.xlsx) | [Main](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Record_Layout_FY2023_Q4.pdf), [worksites](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Worksite_Record_Layout_FY2023_Q4.pdf) |
| FY2024 Q4 | 2023-10-01 to 2024-09-30 | 2024-11-15 | [Main](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2024_Q4.xlsx) | [Worksites](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Worksites_FY2024_Q4.xlsx) | [Main](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Record_Layout_FY2024_Q4.pdf), [worksites](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Worksites_Record_Layout_FY2024_Q4.pdf) |
| FY2025 Q4 | 2024-10-01 to 2025-09-30 | 2025-12-19 | [Main](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q4.xlsx) | [Worksites](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Worksites_FY2025_Q4.xlsx) | [Main](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Record_Layout_FY2025_Q4.pdf), [worksites](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Worksites_Record_Layout_FY2025_Q4.pdf) |
| FY2026 Q3 | 2025-10-01 to 2026-06-30 | 2026-08-14 | [Main](https://www.dol.gov/media/LCA_Disclosure_Data_FY2026_Q3.xlsx) | [Worksites](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/FY26Q3/LCA_Worksites_FY_2026_Q3.xlsx) | [Main](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/FY26Q3/LCA_Record_Layout_FY2026_Q3.pdf), [worksites](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/FY26Q3/LCA_Worksites_Record_Layout_FY2026_Q3.pdf) |

The linked filenames matter. The FY2026 Q3 main-file label on the DOL page says
`LCA_Dislclosure_Data_FY2026_Q3.xlsx`, while the actual link is
`LCA_Disclosure_Data_FY2026_Q3.xlsx`. Its worksite label omits the extra
underscore in the linked `LCA_Worksites_FY_2026_Q3.xlsx`. The page's FY2024
main and worksite layout links return 404; the Q4 layout links above work.

Copies of the ten main and worksite record layouts are saved in
[source-layouts](source-layouts/) with their original filenames. The
[SHA-256 list](source-layouts/SHA256SUMS) identifies the copies reviewed here.
The DOL links in the table remain the source of record. These saved PDFs are
small reference files; the Excel disclosure files are not in the repository.

The DOL page says quarterly files are cumulative within their fiscal year and
show a case based on its most recent determination. It also warns that a small
share of determinations may change in later releases. Use the Q4 files for
completed fiscal years and the Q3 file for FY2026. Do not append Q1 through Q4
of the same year. Even across selected releases, compare `CASE_NUMBER` values
before deciding how to handle repeated or revised cases.

## Excel headers checked

The first worksheet's header row was read from each linked Excel file using
HTTP byte ranges. Full workbooks and data rows were not downloaded or profiled.
The published PDF layouts were inspected separately.

| Release | Main columns | Worksite columns | Change in main header from previous selected release |
| --- | ---: | ---: | --- |
| FY2022 Q4 | 96 | 22 | Starting layout |
| FY2023 Q4 | 96 | 22 | None |
| FY2024 Q4 | 97 | 22 | `EMPLOYER_FEIN` added |
| FY2025 Q4 | 98 | 22 | `LAWFIRM_BUSINESS_FEIN` added |
| FY2026 Q3 | 98 | 22 | None |

The remaining header names kept the same order across these releases. The
worksite header is identical across all five. We have not checked how often
these columns are populated.

The main file includes `CASE_NUMBER`, `CASE_STATUS`, `RECEIVED_DATE`,
`DECISION_DATE`, `ORIGINAL_CERT_DATE`, `VISA_CLASS`, `JOB_TITLE`, `SOC_CODE`,
`SOC_TITLE`, `EMPLOYER_NAME`, `TOTAL_WORKER_POSITIONS`, employment-basis fields,
and a first worksite with location and wage fields. The separate worksite
files contain case number, location, wage, worker count, and secondary-entity
fields.

The [FY2026 main layout](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/FY26Q3/LCA_Record_Layout_FY2026_Q3.pdf)
defines `CASE_STATUS` as the status of the last significant event or decision,
and `DECISION_DATE` as that event's date. `ORIGINAL_CERT_DATE` is the original
certification date for a `Certified-Withdrawn` application. An event-quarter
count must therefore specify which event and status it uses.

`TOTAL_WORKER_POSITIONS` is workers requested on the application. It is not a
case count or a number of hires. The main layout identifies its worksite fields
as the first worksite. The [worksite layout](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/FY26Q3/LCA_Worksites_Record_Layout_FY2026_Q3.pdf)
describes variable-length records with potentially several locations per case.
It also includes `SECONDARY_ENTITY` and `SECONDARY_ENTITY_BUSINESS_NAME` for
client-site placements. These are separate from the filing employer.

Wage fields occur on the first worksite in the main file and in the worksite
file. Units can be Hour, Week, Bi-Weekly, Month, or Year. Pay offers and
prevailing wages have separate units. Keep the original amounts and units.
