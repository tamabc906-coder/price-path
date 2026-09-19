import math
from datetime import date, timedelta

import numpy as np
import pandas as pd

from model import cone, conformal, regime
from model.features import PATH_COLS, build_features, frame


def _bars(n=400, seed=1, p0=20.0):
    rnd = np.random.default_rng(seed)
    out, c, d = [], p0, date(2024, 1, 1)
    for i in range(n):
        o = c
        c = o * math.exp(rnd.normal(0, 0.02))
        h, l = max(o, c) * 1.01, min(o, c) * 0.99
        out.append({"d": d + timedelta(days=i), "o": o, "h": h, "l": l, "c": c, "v": int(1e5 * (1 + rnd.random())), "t": 0})
    return out


def test_features_no_lookahead():
    b = _bars()
    f1 = build_features(frame(b))
    b2 = [dict(x) for x in b]
    for x in b2[300:]:                      # đổi nến tương lai
        x["c"] *= 1.5; x["h"] *= 1.5; x["v"] *= 3
    f2 = build_features(frame(b2))
    cols = [c for c in f1.columns if c not in PATH_COLS and not c.startswith(("fr", "y")) and c != "d"]
    pd.testing.assert_frame_equal(f1.loc[:279, cols], f2.loc[:279, cols])  # tới hàng 279 mọi cửa sổ (≤20) chưa chạm 300


def test_features_labels_and_paths():
    f = build_features(frame(_bars()))
    i = 100
    assert math.isclose(f.loc[i, "fr20"], math.log(f.loc[i + 20, "c"] / f.loc[i, "c"]))
    assert math.isclose(f.loc[i, "p20"], f.loc[i, "fr20"])
    assert f["p20"].isna().tail(20).all()
    assert f.loc[i, "upvol_share"] >= 0 and f.loc[i, "upvol_share"] <= 1
    assert set(f["st_up"].dropna().unique()) <= {True, False}


def test_regime_key_and_shrinkage():
    row = {"vol20_rank": 0.9, "upvol_share": 0.7, "st_up": True, "spike3": True, "climax3": False, "gap_big": False}
    k = regime.regime_key(row)
    assert k == ("high", "high", "up", "yes", "no", "no")
    assert "KL dồn phiên tăng" in regime.chips(k) and "" not in regime.chips(k)
    assert regime.regime_key({**row, "vol20_rank": float("nan")}) is None
    pools = {(): np.zeros((500, 20), np.float32), ("high",): np.zeros((300, 20), np.float32),
             ("high", "high"): np.zeros((50, 20), np.float32)}
    p, level, n = regime.pool_for(k, pools, min_n=200)
    assert level == 5 and n == 300                     # rớt về ô 1 trục vì ô 2 trục chỉ 50 mẫu
    p, level, n = regime.pool_for(("low",) * 6, pools, min_n=200)
    assert level == 6 and n == 500


def test_build_pools_normalizes_by_vol():
    f = build_features(frame(_bars(600)))
    keys = regime.keys_for(f)
    pools = regime.build_pools(f, keys)
    g = pools[()]
    assert g.shape[1] == 20 and len(g) > 200
    # tổng 20 bước × vol20 ≈ fr20
    ok = keys.notna() & f[PATH_COLS].notna().all(axis=1) & (f["vol20"] > 0)
    i0 = f.index[ok][0]
    assert math.isclose(g[0].sum() * f.loc[i0, "vol20"], f.loc[i0, "fr20"], rel_tol=1e-4)


def test_cone_clip_and_quantiles():
    pool = np.full((100, 20), 5.0, np.float32)         # bước cực lớn → phải bị kẹp ±ln 1,07
    paths = cone.simulate(0.02, pool, n=50, seed=1)
    assert paths.shape == (50, 20)
    assert np.allclose(paths[:, 0], math.log(1.07))
    q = cone.quantiles(paths, 10.0)
    assert q[5][50] == round(10.0 * math.exp(5 * math.log(1.07)), 2)
    assert cone.seed_for("HPG", "2026-09-19") == cone.seed_for("HPG", "2026-09-19")
    assert cone.simulate(0.02, pool, n=5, seed=3).tolist() == cone.simulate(0.02, pool, n=5, seed=3).tolist()


def test_scenarios_two_clusters():
    up = np.cumsum(np.full((60, 20), 0.01), axis=1)
    dn = np.cumsum(np.full((40, 20), -0.01), axis=1)
    sc = cone.scenarios(np.vstack([up, dn]).astype(np.float32), 10.0, seed=1)
    assert [s["name"] for s in sc] == ["A", "B"] and sc[0]["weight"] == 0.6
    assert sc[0]["path"][-1] > 10 > sc[1]["path"][-1]


def test_conformal_adjust_and_update():
    st = conformal.new_state()
    q = {5: -0.10, 10: -0.07, 25: -0.03, 50: 0.0, 75: 0.03, 90: 0.07, 95: 0.10}
    assert conformal.adjust(q, st, 10) == q                     # s = 1 → nguyên
    for _ in range(30):
        conformal.update(st, 10, 80, 0.60)                      # trúng ít → nới
    assert conformal.scale(st, 10, 80) > 1.0
    a = conformal.adjust(q, st, 10)
    assert a[10] < q[10] and a[90] > q[90] and a[50] == 0.0 and a[25] == q[25]
    for _ in range(200):
        conformal.update(st, 10, 80, 1.0)                       # trúng hết → co, kẹp S_MIN
    assert conformal.scale(st, 10, 80) >= conformal.S_MIN
    assert conformal.coverage(st, 10, 80, last=10) == 1.0
    assert len(st["levels"]["10"]["80"]["hits"]) <= conformal.WINDOW
    assert conformal.hit(a, 0.0, 80) and not conformal.hit(a, 0.5, 90)
