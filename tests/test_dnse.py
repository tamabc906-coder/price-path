from datetime import datetime

from common import dnse
from common.config import TZ


def test_parse_sorts_and_skips_bad_rows():
    t1 = int(datetime(2026, 9, 18, 0, 0, tzinfo=TZ).timestamp())
    t0 = int(datetime(2026, 9, 17, 0, 0, tzinfo=TZ).timestamp())
    p = {"t": [t1, t0, "x"], "o": [1, 2, 3], "h": [2, 3, 4], "l": [0.5, 1, 2], "c": [1.5, 2.5, 3], "v": [10, 20, 30]}
    b = dnse._parse(p)
    assert [x["d"].isoformat() for x in b] == ["2026-09-17", "2026-09-18"]
    assert b[0]["c"] == 2.5 and b[0]["v"] == 20


def test_session_settled_needs_atc_bar():
    mk = lambda hh, mm: {"t": int(datetime(2026, 9, 18, hh, mm, tzinfo=TZ).timestamp())}
    assert not dnse.session_settled([])
    assert not dnse.session_settled([mk(13, 45)])
    assert dnse.session_settled([mk(14, 45)])


def test_merge_today_prefers_more_volume():
    d = datetime(2026, 9, 18, tzinfo=TZ).date()
    daily = {"d": d, "o": 1, "h": 2, "l": 1, "c": 1.5, "v": 100, "t": 0}
    minutes = [{"d": d, "o": 1, "h": 3, "l": 1, "c": 2, "v": 150, "t": 1}]
    assert dnse.merge_today(daily, minutes)["v"] == 150
    minutes[0]["v"] = 50
    assert dnse.merge_today(daily, minutes) is daily
