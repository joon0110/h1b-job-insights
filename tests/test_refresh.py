import json

import pandas as pd
import pytest

from h1b_job_insights import activity_data, activity_predict, activity_train, refresh
from h1b_job_insights.activity_data import quarter_number
from tests.test_activity_models import panel
from tests.test_pipeline import MAIN_HEADERS, workbook


def test_new_excel_advances_training_and_forecast(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    processed = tmp_path / "processed"
    models = tmp_path / "models"
    monkeypatch.setattr(
        activity_train,
        "CANDIDATES",
        {
            "random_forest": [{"n_estimators": 4, "max_depth": 2, "min_samples_leaf": 2}],
            "xgboost": [{"n_estimators": 4, "max_depth": 2, "learning_rate": 0.1}],
        },
    )
    headers = (*MAIN_HEADERS, "TOTAL_WORKER_POSITIONS")
    for release, group in panel(20).groupby("FISCAL_QUARTER"):
        year = int(release[2:6])
        quarter = int(release[-1])
        month = (10, 1, 4, 7)[quarter - 1]
        date = f"{year - 1 if quarter == 1 else year}-{month:02d}-05"
        rows = []
        for row in group.loc[group.LCA_CASES.gt(0)].itertuples():
            values = {
                "CASE_NUMBER": f"{release}-{row.EMPLOYER_ID}",
                "CASE_STATUS": "Certified",
                "VISA_CLASS": "H-1B",
                "EMPLOYER_NAME": row.EMPLOYER_NAME,
                "RECEIVED_DATE": date,
                "DECISION_DATE": date,
                "TOTAL_WORKER_POSITIONS": 1,
            }
            rows.append(tuple(values.get(header) for header in headers))
        workbook(raw / f"LCA_Disclosure_Data_{release}.xlsx", headers, rows)
        if release not in ("FY2026_Q3", "FY2026_Q4"):
            continue
        result = refresh.run(raw, processed, models, jobs=1)
        expected_target = "FY2026_Q4" if release == "FY2026_Q3" else "FY2027_Q1"
        assert result == {"trained_through": release, "target_quarter": expected_target}
        history, prediction = activity_predict.predict("Company 0", processed / "activity", models)
        assert history.FISCAL_QUARTER.max() == release
        assert prediction.target_quarter.tolist() == [expected_target]
        bundle = activity_predict.load_bundle(processed / "activity", models)
        assert bundle["selection"]["trend_constraints"] == activity_train.TREND_CONSTRAINTS
        assert bundle["trained_through"] == quarter_number(release)
        manifest = json.loads((processed / "activity" / "panel_manifest.json").read_text())
        assert manifest["latest_source_release"] == release
        assert manifest["quarter_cases"][release] == len(rows)

    latest = processed / "main" / "fy2026_q4.parquet"
    frame = pd.read_parquet(latest)
    frame["RECEIVED_DATE"] = "2026-10-05"
    frame.to_parquet(latest, index=False)
    (processed / "activity" / "panel_manifest.json").unlink()
    with pytest.raises(ValueError, match="empty quarter"):
        activity_data.prepare_panel(processed, processed / "activity")
