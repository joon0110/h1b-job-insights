import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from h1b_job_insights import activity_features as features
from h1b_job_insights import activity_predict, normalize
from h1b_job_insights import activity_train as train
from h1b_job_insights.activity_data import quarter_number, sha256
from h1b_job_insights.company_activity import quarter_label
from tests.check_constraints import check_monotonicity
from tests.check_models import evaluate


def panel():
    random = np.random.default_rng(42)
    records = []
    first = quarter_number("FY2022_Q1")
    for company in range(30):
        name = f"COMPANY {company}"
        for t in range(18):
            cases = 1 if t == 0 else int(random.random() < (0.15 + company / 50)) * (company + 1)
            records.append((normalize.employer_id(name), name, quarter_label(first + t), cases))
    return pd.DataFrame(
        records, columns=["EMPLOYER_ID", "EMPLOYER_NAME", "FISCAL_QUARTER", "LCA_CASES"]
    )


def test_future_changes_do_not_change_past_company_or_market_inputs():
    frame = panel()
    origin = quarter_number("FY2025_Q4")
    before = features.build_examples(frame, [origin])
    frame.loc[frame.FISCAL_QUARTER.gt("FY2025_Q4"), "LCA_CASES"] = 999
    after = features.build_examples(frame, [origin])
    pd.testing.assert_frame_equal(before[features.FEATURES], after[features.FEATURES])
    assert set(before.horizon) == {1, 2}
    assert set(before.target_quarter) == {origin + 1, origin + 2}
    assert after.target_active.eq(1).all()
    assert not before.target_active.equals(after.target_active)
    assert "target_active" not in features.FEATURES
    assert "target_cases" not in features.FEATURES


def test_live_inputs_match_historical_inputs_and_unknown_labels_stay_missing():
    frame = panel()
    origin = quarter_number("FY2025_Q4")
    historical = features.build_examples(frame, [origin])
    live = features.build_examples(frame.loc[frame.FISCAL_QUARTER.le("FY2025_Q4")], [origin])
    pd.testing.assert_frame_equal(historical[features.FEATURES], live[features.FEATURES])
    assert live.target_active.isna().all()
    examples = features.build_examples(frame)
    training, evaluation = train.split_at(examples, origin)
    assert examples.loc[training, "target_quarter"].max() == origin
    assert examples.loc[evaluation, "target_quarter"].min() > origin


def test_short_history_and_missing_quarters():
    frame = panel()
    late_name = "LATE COMPANY"
    late = pd.DataFrame(
        [(normalize.employer_id(late_name), late_name, f"FY2026_Q{q}", 1) for q in (1, 2)],
        columns=frame.columns,
    )
    examples = features.build_examples(pd.concat([frame, late]))
    assert late_name not in set(examples.EMPLOYER_NAME)
    assert examples.history_quarters.min() == 4
    with pytest.raises(ValueError, match="without gaps"):
        features.build_examples(frame.drop(index=[5]))


def test_xgboost_respects_trend_and_inactivity_directions():
    random = np.random.default_rng(9)
    frame = pd.DataFrame(
        random.normal(size=(3000, len(features.FEATURES))), columns=features.FEATURES
    ).astype("float32")
    frame["inactive_quarters"] = random.integers(0, 8, len(frame)).astype("float32")
    score = 2 * frame.recent_slope - 0.8 * frame.inactive_quarters + 2
    labels = (random.random(len(frame)) < 1 / (1 + np.exp(-score))).astype(int)
    model = train.make_model(
        "xgboost",
        {
            "n_estimators": 60,
            "max_depth": 3,
            "learning_rate": 0.1,
            "monotone_constraints": train.TREND_CONSTRAINTS,
        },
        jobs=1,
    )
    model.fit(frame, labels)
    report = check_monotonicity(model, frame).set_index("feature")
    assert report.violations.sum() == 0
    assert report.loc["recent_slope", "rows_with_change"] > 0
    assert report.loc["inactive_quarters", "rows_with_change"] > 0
    assert np.ptp(model.predict_proba(frame)[:, 1]) > 0.2


def test_training_query_and_random_forest_reuse(tmp_path, monkeypatch):
    data_dir = tmp_path / "data" / "activity"
    data_dir.mkdir(parents=True)
    frame = panel()
    frame.to_parquet(data_dir / "company_quarters.parquet", index=False)
    examples = features.build_examples(frame)
    examples.to_parquet(data_dir / "examples.parquet", index=False)
    manifest = {
        "features": features.FEATURES,
        "feature_code_sha256": sha256(Path(features.__file__)),
        "examples_sha256": sha256(data_dir / "examples.parquet"),
        "panel_sha256": sha256(data_dir / "company_quarters.parquet"),
        "last_quarter": "FY2026_Q2",
        "version": {"sources": [["FY2026_Q3", "source-hash"]]},
    }
    (data_dir / "manifest.json").write_text(json.dumps(manifest))
    (data_dir.parent / "source_manifest.json").write_text(
        json.dumps({"files": [{"kind": "main", "release": "FY2026_Q3", "sha256": "source-hash"}]})
    )
    monkeypatch.setattr(
        train,
        "CANDIDATES",
        {
            "random_forest": [{"n_estimators": 8, "max_depth": 3, "min_samples_leaf": 2}],
            "xgboost": [{"n_estimators": 8, "max_depth": 2, "learning_rate": 0.1}],
        },
    )
    model_dir = tmp_path / "models"
    selection = train.run(data_dir, model_dir, jobs=1)
    assert sorted(path.name for path in model_dir.iterdir()) == ["classifiers.joblib"]
    history, result = activity_predict.predict("company 0", data_dir, model_dir)
    assert len(history) == 18
    assert result.target_quarter.tolist() == ["FY2026_Q3"]
    assert result.probability.between(0, 1).all()
    bundle = joblib.load(model_dir / "classifiers.joblib")
    assert bundle["trained_through"] == quarter_number("FY2026_Q2")
    assert bundle["training_rows"] == examples.target_active.notna().sum()
    live = examples.loc[
        examples.EMPLOYER_NAME.eq("COMPANY 0")
        & examples.origin.eq(bundle["trained_through"])
        & examples.horizon.eq(1)
    ]
    for name, model in bundle["models"].items():
        _, result = activity_predict.predict("company 0", data_dir, model_dir, name)
        expected = model.predict_proba(live[features.FEATURES])[:, 1]
        if selection["use_calibration"][name]:
            expected = train.calibrate(bundle["calibrators"][name], expected)
        np.testing.assert_allclose(result.probability, expected)
    model_hash = sha256(model_dir / "classifiers.joblib")
    fit_at = train.fit_at
    cutoffs = []

    def historical_fit(frame, name, parameters, origin, jobs):
        mask, _ = train.split_at(frame, origin)
        cutoffs.append(frame.loc[mask, "target_quarter"].max())
        return fit_at(frame, name, parameters, origin, jobs)

    with monkeypatch.context() as patch:
        patch.setattr(train, "fit_at", historical_fit)
        predictions, metrics = evaluate(data_dir, model_dir, tmp_path / "checks", jobs=1)
    cutoff = quarter_number("FY2025_Q4")
    assert cutoffs == [cutoff, cutoff]
    assert predictions.origin.eq(cutoff).all()
    assert set(predictions.target_quarter) == {cutoff + 1, cutoff + 2}
    assert len(predictions) == 60
    assert len(metrics) == 15
    assert sha256(model_dir / "classifiers.joblib") == model_hash
    with pytest.raises(ValueError, match="separate directory"):
        evaluate(data_dir, model_dir, model_dir, jobs=1)
    make_model = train.make_model

    def only_xgboost(name, *args, **kwargs):
        assert name == "xgboost", "Random Forest should be reused"
        return make_model(name, *args, **kwargs)

    monkeypatch.setattr(train, "make_model", only_xgboost)
    constrained_dir = tmp_path / "constrained"
    constrained = train.run(
        data_dir, constrained_dir, jobs=1, constrain_trends=True, reuse_random_forest=model_dir
    )
    assert constrained["trend_constraints"] == train.TREND_CONSTRAINTS
    assert sorted(path.name for path in constrained_dir.iterdir()) == ["classifiers.joblib"]
    reused = joblib.load(constrained_dir / "classifiers.joblib")
    np.testing.assert_array_equal(
        bundle["models"]["random_forest"].predict_proba(examples[features.FEATURES]),
        reused["models"]["random_forest"].predict_proba(examples[features.FEATURES]),
    )
    _, constrained_query = activity_predict.predict("company 0", data_dir, constrained_dir)
    expected = reused["models"]["xgboost"].predict_proba(live[features.FEATURES])[:, 1]
    if constrained["use_calibration"]["xgboost"]:
        expected = train.calibrate(reused["calibrators"]["xgboost"], expected)
    np.testing.assert_allclose(constrained_query.probability, expected)
    with pytest.raises(ValueError, match="separate output"):
        train.run(data_dir, model_dir, reuse_random_forest=model_dir)
    with pytest.raises(ValueError, match="No H-1B"):
        activity_predict.predict("missing", data_dir, model_dir)
    (data_dir / "examples.parquet").write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        activity_predict.predict("company 0", data_dir, model_dir)
