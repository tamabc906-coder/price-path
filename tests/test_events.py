import math
from datetime import date, timedelta

import numpy as np

from model import events


def _bars(n=300, seed=3, p0=30.0):
    rnd = np.random.default_rng(seed)
    out, c, d = [], p0, date(2024, 1, 1)
    for i in range(n):
        o = c * math.exp(rnd.normal(0, 0.01))
        c = o * math.exp(rnd.normal(0, 0.025))
        out.append({"d": d + timedelta(days=i), "o": o, "h": max(o, c) * 1.01, "l": min(o, c) * 0.99, "c": c,
                    "v": int(1e5 * (1 + 3 * rnd.random())), "t": 0})
    return out


def test_no_lookahead():
    b = _bars()
    e1 = events.detect(b)
    b2 = [dict(x) for x in b]
    for x in b2[250:]:
        x["c"] *= 0.5; x["l"] *= 0.5; x["o"] *= 0.6; x["v"] *= 5
    e2 = events.detect(b2)
    for k in events.CODES:
        assert (e1[k].to_numpy()[:250] == e2[k].to_numpy()[:250]).all(), k


def test_dedup_keeps_first_in_window():
    raw = np.array([1, 1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1], dtype=bool)
    assert np.flatnonzero(events.dedup(raw, 5)).tolist() == [0, 6, 12]


def test_gap_fill_demand_fires():
    # 70 phiên đi ngang ở 30, 10 phiên giảm về 26, rồi: nến đỏ gap xuống ≥ 1 %, nến xanh đóng trên mở cửa nến đỏ
    b, d = [], date(2024, 1, 1)
    def add(o, c, v=1e5):
        b.append({"d": d + timedelta(days=len(b)), "o": o, "h": max(o, c) * 1.005, "l": min(o, c) * 0.995, "c": c, "v": int(v), "t": 0})
    for _ in range(70):
        add(30, 30)
    for k in range(10):
        add(30 - 0.4 * k, 30 - 0.4 * (k + 1))
    a_close = b[-1]["c"]                       # 26
    add(a_close * 0.98, a_close * 0.96)        # đỏ, mở gap −2 %
    add(a_close * 0.96, a_close * 0.99)        # xanh, đóng trên mở của nến đỏ
    e = events.detect(b)
    assert bool(e["gap_fill_demand"].iloc[-1])


def test_pool_steps_and_widen():
    import pandas as pd
    from model.features import PATH_COLS
    rows = pd.DataFrame([[0.01 * (k + 1) for k in range(20)] + [0.02]], columns=PATH_COLS + ["vol20"])
    st = events.pool_steps(rows)
    assert st.shape == (1, 20) and np.allclose(st, 0.5)
    q = {5: -0.1, 10: -0.08, 25: -0.04, 50: 0.0, 75: 0.04, 90: 0.08, 95: 0.1}
    w = events.widen(q, {"50": 1.0, "80": 1.5, "90": 2.0})
    assert w[50] == 0 and w[25] == -0.04 and np.isclose(w[90], 0.12) and np.isclose(w[5], -0.2)
