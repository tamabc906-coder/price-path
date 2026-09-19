import numpy as np
import pandas as pd

from model import direction


def test_matrix_handles_bool_and_missing():
    f = pd.DataFrame({"r1": [0.1, np.nan], "st_up": [True, False], "spike3": [False, True]})
    m = direction.matrix(f)
    assert m.shape == (2, len(direction.FEATURES)) and m.dtype == np.float32
    j = direction.FEATURES.index("st_up")
    assert m[0, j] == 1.0 and m[1, j] == 0.0
    assert np.isnan(m[0, direction.FEATURES.index("idx_r5")])   # cột thiếu → NaN


def _row(year, bl, bf, acc, up):
    return {"year": year, "brier_lgbm": bl, "brier_freq": bf, "acc_lgbm": acc, "acc_always_up": up}


def test_gate_requires_both_conditions_on_full_years_only():
    good = [_row(y, 0.24, 0.25, 0.60, 0.55) for y in range(2021, 2026)]
    bad_last = _row(2026, 0.30, 0.25, 0.40, 0.55)          # năm chưa trọn, bỏ qua
    g = direction.gate({5: good + [bad_last], 10: good + [bad_last]}, last_year=2026)
    assert g["enabled"] and g["per_h"]["5"]["wins_brier"] == "5/5"
    weak = good[:3] + [_row(2024, 0.26, 0.25, 0.50, 0.55), _row(2025, 0.26, 0.25, 0.50, 0.55)]
    g = direction.gate({5: good, 10: weak}, last_year=2026)
    assert not g["enabled"] and g["per_h"]["5"]["enabled"] and not g["per_h"]["10"]["enabled"]
    assert not direction.gate({}, 2026)["enabled"]


def test_load_booster_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(direction, "ARTIFACTS", tmp_path)
    assert direction.load_booster(5) is None
