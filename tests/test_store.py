from datetime import date

from common import store


def _bar(d, c, v=100):
    return {"d": date.fromisoformat(d), "o": c, "h": c + 1, "l": c - 1, "c": c, "v": v, "t": 0}


def test_merge_appends_and_overwrites_same_day():
    st = store.empty()
    assert store.merge(st, "HPG", [_bar("2026-09-17", 25.0), _bar("2026-09-18", 26.0)]) == 2
    # nến 18/09 được nguồn sửa khối lượng, thêm nến 19/09
    n = store.merge(st, "HPG", [_bar("2026-09-18", 26.0, v=200), _bar("2026-09-19", 27.0)])
    assert n == 2
    rows = st["bars"]["HPG"]
    assert [r[0] for r in rows] == ["2026-09-17", "2026-09-18", "2026-09-19"]
    assert rows[1][5] == 200
    # nối lại y hệt → không đổi gì
    assert store.merge(st, "HPG", [_bar("2026-09-19", 27.0)]) == 0


def test_roundtrip_to_bars_keeps_dates_and_order():
    st = store.empty()
    store.merge(st, "X", [_bar("2026-01-03", 2.0), _bar("2026-01-02", 1.0)])
    b = store.bars(st, "X")
    assert [x["d"].isoformat() for x in b] == ["2026-01-02", "2026-01-03"]
    assert b[0]["c"] == 1.0 and isinstance(b[0]["v"], int)
    assert store.span(st, "X") == ("2026-01-02", "2026-01-03", 2)
    assert store.span(st, "NONE") == ("", "", 0)


def test_save_load_compact(tmp_path):
    st = store.empty()
    store.merge(st, "X", [_bar("2026-01-02", 1.0)])
    p = tmp_path / "h.json"
    store.save(st, p)
    assert "\n" not in p.read_text(encoding="utf-8")
    back = store.load(p)
    assert back["bars"]["X"][0][0] == "2026-01-02" and back["updated_at"]
    assert store.load(tmp_path / "missing.json")["bars"] == {}


class _FakeClient:
    def __init__(self):
        self.calls = []

    def daily(self, sym, days=None):
        self.calls.append(("stock", sym, days))
        return [_bar("2026-01-02", 1.0)]

    def index(self, sym, days=None):
        self.calls.append(("index", sym, days))
        return [_bar("2026-01-02", 1000.0)]


def test_ensure_fetches_only_missing_and_index():
    st = store.empty()
    store.merge(st, "HPG", [_bar("2026-01-02", 1.0)])
    c = _FakeClient()
    got = store.ensure(st, [{"symbol": "HPG", "company_name": "Hoà Phát", "exchange": "HOSE"},
                            {"symbol": "NEW", "company_name": "Mới", "exchange": "HNX"}], c, days=123)
    assert got == ["NEW", "VNINDEX"]
    assert c.calls == [("stock", "NEW", 123), ("index", "VNINDEX", 123)]
    assert st["symbols"]["NEW"]["exchange"] == "HNX" and st["symbols"]["VNINDEX"]["exchange"] == "index"
