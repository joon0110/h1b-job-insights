# H-1B Job Insights

H-1B Job Insights is a work in progress. It will help job seekers examine historical
H-1B Labor Condition Application (LCA) records for a company, role, and worksite.
The source will be public disclosure data from the U.S. Department of Labor.

An LCA is not a USCIS petition, visa approval, or record of a hire. Historical LCA
activity cannot tell an applicant whether a company will sponsor them.

The project will keep three kinds of results distinct: records observed in the DOL
data, metrics calculated from those records, and forecasts produced by a model.
The [DOL source review](docs/data-sources.md) records the selected releases and
observed schema differences.

## Development setup

Use Python 3.11 or newer. [pyproject.toml](pyproject.toml) tells pip to build the
package with setuptools and find its code under `src/`. To install only the
package, run `python -m pip install .`. For development, use the editable install
below: `-e` picks up local code changes without reinstalling, and `[dev]` adds
pytest and Ruff.

On a machine with Python 3.13:

```sh
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
ruff check .
```

Raw DOL files belong under `data/raw/`; generated data belongs under
`data/processed/`. Both locations are ignored by Git.
