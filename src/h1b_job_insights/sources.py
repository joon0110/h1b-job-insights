import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class Source:
    release: str
    kind: str
    url: str | None
    local_filename: str | None = None

    @property
    def filename(self) -> str:
        if self.local_filename is not None:
            return self.local_filename
        if self.url is None:
            raise ValueError("A source needs a URL or local filename")
        return Path(urlparse(self.url).path).name


SOURCES = (
    Source(
        "FY2022_Q1",
        "main",
        "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q1.xlsx",
    ),
    Source(
        "FY2022_Q2",
        "main",
        "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q2.xlsx",
    ),
    Source(
        "FY2022_Q3",
        "main",
        "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q3.xlsx",
    ),
    Source(
        "FY2022_Q4",
        "main",
        "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2022_Q4.xlsx",
    ),
    Source(
        "FY2022_Q4",
        "worksites",
        "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Worksites_FY2022_Q4.xlsx",
    ),
    Source(
        "FY2023_Q1",
        "main",
        "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q1.xlsx",
    ),
    Source(
        "FY2023_Q2",
        "main",
        "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q2.xlsx",
    ),
    Source(
        "FY2023_Q3",
        "main",
        "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q3.xlsx",
    ),
    Source(
        "FY2023_Q4",
        "main",
        "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2023_Q4.xlsx",
    ),
    Source(
        "FY2023_Q4",
        "worksites",
        "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Worksites_FY2023_Q4.xlsx",
    ),
    Source(
        "FY2024_Q1",
        "main",
        "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2024_Q1.xlsx",
    ),
    Source(
        "FY2024_Q2",
        "main",
        "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2024_Q2.xlsx",
    ),
    Source(
        "FY2024_Q3",
        "main",
        "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2024_Q3.xlsx",
    ),
    Source(
        "FY2024_Q4",
        "main",
        "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2024_Q4.xlsx",
    ),
    Source(
        "FY2024_Q4",
        "worksites",
        "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Worksites_FY2024_Q4.xlsx",
    ),
    Source(
        "FY2025_Q1",
        "main",
        "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q1.xlsx",
    ),
    Source(
        "FY2025_Q2",
        "main",
        "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q2.xlsx",
    ),
    Source(
        "FY2025_Q3",
        "main",
        "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q3.xlsx",
    ),
    Source(
        "FY2025_Q4",
        "main",
        "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q4.xlsx",
    ),
    Source(
        "FY2025_Q4",
        "worksites",
        "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Worksites_FY2025_Q4.xlsx",
    ),
    Source(
        "FY2026_Q3",
        "main",
        "https://www.dol.gov/media/LCA_Disclosure_Data_FY2026_Q3.xlsx",
    ),
    Source(
        "FY2026_Q3",
        "worksites",
        "https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/FY26Q3/LCA_Worksites_FY_2026_Q3.xlsx",
    ),
)

MAIN_FILENAME = re.compile(r"LCA_Disclosure_Data_(FY20\d{2}_Q[1-4])\.xlsx", re.IGNORECASE)
WORKSITE_FILENAME = re.compile(r"LCA_Worksites_(FY_?20\d{2}_Q[1-4])\.xlsx", re.IGNORECASE)


def discover_sources(raw_dir: Path) -> tuple[Source, ...]:
    known = {source.filename: source for source in SOURCES}
    selected = [source for source in SOURCES if (raw_dir / source.filename).is_file()]
    extras = []
    for path in sorted(raw_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() != ".xlsx" or path.name.startswith("~$"):
            continue
        if path.name in known:
            continue
        main = MAIN_FILENAME.fullmatch(path.name)
        worksites = WORKSITE_FILENAME.fullmatch(path.name)
        if main:
            extras.append(Source(main.group(1).upper(), "main", None, path.name))
        elif worksites:
            release = worksites.group(1).upper().replace("FY_", "FY")
            extras.append(Source(release, "worksites", None, path.name))
        else:
            raise ValueError(f"Unrecognized Excel filename in {raw_dir}: {path.name}")
    sources = tuple([*selected, *extras])
    if not sources:
        raise FileNotFoundError(f"No DOL Excel workbooks found in {raw_dir}")
    keys = [(source.release, source.kind) for source in sources]
    if len(keys) != len(set(keys)):
        raise ValueError(f"More than one workbook for the same release and kind in {raw_dir}")
    return sources
