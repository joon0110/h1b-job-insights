import numpy as np
import pandas as pd
import pytest

from tests.check_models import reliability, scores


def test_probability_scores_and_band_boundaries():
    result = scores([0, 1], [0.25, 0.75])
    assert result["brier"] == pytest.approx(0.0625)
    assert result["log_loss"] == pytest.approx(-np.log(0.75))
    assert scores([0, 0], [0.1, 0.2])["roc_auc"] is None
    frame = pd.DataFrame({"target_active": [0, 0, 1, 1], "xgboost": [0, 0.9, 0.99, 1]})
    table = reliability(frame, "xgboost").set_index("probability_band")
    assert table.loc["0–10%", "rows"] == 1
    assert table.loc["90–100%", "rows"] == 3
    assert table.loc["90–100%", "actual_rate"] == pytest.approx(2 / 3)
    assert table.loc[">=99%", "rows"] == 2


@pytest.mark.parametrize("actual,probability", [([0.5], [0.2]), ([1], [np.nan]), ([0], [1.1])])
def test_invalid_outcomes_and_probabilities_fail(actual, probability):
    with pytest.raises(ValueError, match="Invalid"):
        scores(actual, probability)
