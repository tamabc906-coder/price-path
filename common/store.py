"""Kho nến ngày dài hạn: data/history.json — 39 mã + VNINDEX, ~7 năm, commit trong repo.

Vì sao có kho riêng: DNSE lùi được ~7 năm nhưng gọi 40 mã × 4000 ngày mỗi phiên là thừa và dễ bị
chặn; job hằng ngày chỉ lấy 30 ngày gần nhất rồi NỐI vào kho (ghi đè nến trùng ngày — nến hôm qua
đôi khi được nguồn sửa lại khối lượng). Mã mới vào danh mục thì `ensure` tải trọn lịch sử một lần.

Định dạng (gọn, không indent — ~3 MB):
{
  "updated_at": "2026-09-19T15:40:00+07:00",
  "unit": "nghìn đồng, giá điều chỉnh (DNSE)",
  "symbols": {"HPG": {"name": "Hoà Phát", "exchange": "HOSE"}, "VNINDEX": {"name": "VN-Index", "exchange": "index"}},
  "bars": {"HPG": [["2019-11-15", o, h, l, c, v], ...]}       # cũ → mới, ngày ISO
}
Hàng nến trong kho là list để gọn; `to_bars` đổi sang list[dict] {"d": date, "o","h","l","c","v","t"}
đúng khuôn common/dnse.py để dùng chung với job/trend.py, job/patterns.py.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

from .config import HISTORY, INDEX_SYMBOL, TZ

logger = logging.getLogger(__name__)

UNIT = "nghìn đồng, giá điều chỉnh (DNSE)"
# Lịch sử tối đa xin DNSE cho mã mới: 4000 ngày (~11 năm) — nguồn trả tới đâu lấy tới đó.
FULL_DAYS = 4000


def empty() -> dict:
    return {"updated_at": "", "unit": UNIT, "symbols": {}, "bars": {}}


def load(path: Path = HISTORY) -> dict:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return empty()
    d.setdefault("symbols", {})
    d.setdefault("bars", {})
    return d


def save(store: dict, path: Path = HISTORY) -> None:
    store["updated_at"] = datetime.now(TZ).isoformat(timespec="seconds")
    store["unit"] = UNIT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def to_bars(rows: list[list]) -> list[dict]:
    """Hàng kho → list[dict] khuôn dnse (d là date, có t epoch để tương thích)."""
    out = []
    for r in rows:
        d = date.fromisoformat(r[0])
        out.append({"d": d, "o": float(r[1]), "h": float(r[2]), "l": float(r[3]), "c": float(r[4]),
                    "v": int(r[5]), "t": int(datetime(d.year, d.month, d.day, tzinfo=TZ).timestamp())})
    return out


def from_bars(bars: list[dict]) -> list[list]:
    return [[b["d"].isoformat(), b["o"], b["h"], b["l"], b["c"], int(b["v"])] for b in bars]


def merge(store: dict, symbol: str, new_bars: list[dict]) -> int:
    """Nối nến mới vào kho, ghi đè nến trùng ngày. Trả số nến thêm/đổi. Không đụng nến cũ khác."""
    if not new_bars:
        return 0
    rows = {r[0]: r for r in store["bars"].get(symbol, [])}
    changed = 0
    for r in from_bars(new_bars):
        if rows.get(r[0]) != r:
            rows[r[0]] = r
            changed += 1
    store["bars"][symbol] = [rows[k] for k in sorted(rows)]
    return changed


def bars(store: dict, symbol: str) -> list[dict]:
    return to_bars(store["bars"].get(symbol, []))


def span(store: dict, symbol: str) -> tuple[str, str, int]:
    """(ngày đầu, ngày cuối, số nến) — ("", "", 0) nếu chưa có."""
    rows = store["bars"].get(symbol) or []
    return (rows[0][0], rows[-1][0], len(rows)) if rows else ("", "", 0)


def ensure(store: dict, items: list[dict], client, days: int = FULL_DAYS) -> list[str]:
    """Mã trong danh mục (và VNINDEX) chưa có trong kho → tải trọn lịch sử. Trả danh sách mã đã tải."""
    fetched: list[str] = []
    wanted = [(it["symbol"], it.get("company_name") or it.get("name") or "", it.get("exchange") or "")
              for it in items] + [(INDEX_SYMBOL, "VN-Index", "index")]
    for sym, name, exch in wanted:
        store["symbols"].setdefault(sym, {"name": name, "exchange": exch})
        if store["bars"].get(sym):
            continue
        b = client.index(sym, days=days) if sym == INDEX_SYMBOL else client.daily(sym, days=days)
        if not b:
            logger.warning("Không tải được lịch sử %s", sym)
            continue
        merge(store, sym, b)
        fetched.append(sym)
        logger.info("Tải trọn lịch sử %s: %d nến từ %s", sym, len(b), b[0]["d"])
    return fetched


# Giá đóng cửa của cùng một phiên ĐÃ QUA lệch quá ngần này giữa nguồn và kho → nguồn đã điều chỉnh
# giá (GDKHQ: chia thưởng, cổ tức). Nến phiên cuối không tính — nguồn hay sửa lại khối lượng/giá ATC.
ADJ_TOLERANCE = 0.005


def adjusted_symbols(store: dict, new_by_symbol: dict[str, list[dict]]) -> list[tuple[str, str, float]]:
    """Mã mà nguồn vừa điều chỉnh lại giá quá khứ: [(mã, phiên lệch nhiều nhất, tỉ lệ nguồn/kho)].

    Vì sao cần: `merge` chỉ ghi đè đoạn vừa tải, phần cũ hơn giữ nguyên. Khi DNSE hạ giá lịch sử sau
    ngày GDKHQ, kho thành hai hệ giá ghép lại — VPB 26/08/2026 (hệ số 0,793): biểu đồ có cú rơi 20 %
    không có thật, và DNSE điều chỉnh MUỘN (kho dựng 19/09 vẫn nhận giá chưa điều chỉnh), nên đoạn so
    phải dài chứ không chỉ vài phiên quanh ngày GDKHQ.
    """
    out = []
    for sym, bars in new_by_symbol.items():
        rows = {r[0]: r[4] for r in store["bars"].get(sym, [])}
        worst = None
        for b in bars[:-1]:
            old = rows.get(b["d"].isoformat())
            if not old:
                continue
            ratio = b["c"] / old
            if abs(ratio - 1) > ADJ_TOLERANCE and (worst is None or abs(ratio - 1) > abs(worst[1] - 1)):
                worst = (b["d"].isoformat(), round(ratio, 4))
        if worst:
            out.append((sym, worst[0], worst[1]))
    return out


def replace(store: dict, symbol: str, bars: list[dict]) -> None:
    """Thay TOÀN BỘ lịch sử một mã bằng bản mới tải (sau khi nguồn điều chỉnh giá)."""
    store["bars"][symbol] = from_bars(sorted(bars, key=lambda b: b["d"]))
