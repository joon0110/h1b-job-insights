import hashlib
import re
import unicodedata

LEGAL_SUFFIX = re.compile(r"(?:\s*,\s*|\s+)(L\.?L\.?C\.?|L\.?L\.?P\.?|INC\.?|CORP\.?|LTD\.?)$")


def employer_name(value: str | None) -> str | None:
    if value is None:
        return None
    name = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).strip()).upper()
    if not name:
        return None
    return LEGAL_SUFFIX.sub(lambda match: " " + match.group(1).replace(".", ""), name)


def employer_id(name: str) -> str:
    return "emp_" + hashlib.sha256(name.encode()).hexdigest()[:24]
