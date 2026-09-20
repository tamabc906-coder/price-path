"""Kho phiên đã gộp theo mức giá: data/zone/<MÃ>.json — một file mỗi mã, commit trong repo.

{
  "symbol": "FPT",
  "updated_at": "2026-09-22T15:50:00+07:00",
  "sessions": {
    "2026-09-18": {"src": "vnd", "est": false, "close": 71.7, "total": 15500700, "ticks": 12669,
                   "levels": {"74.2": [mua, bán, x, mua_lớn, bán_lớn], ...}},
    "2026-09-17": {"src": "dnse1m", "est": true, "close": 66.5, "total": ..., "levels": {...}}
  }
}

Đơn vị giá: nghìn đồng, ĐÚNG NHƯ NGUỒN LÚC LƯU — tick VNDirect là giá thô, nến 1' DNSE là giá đã điều chỉnh tại
thời điểm tải. Vì thế `close` của phiên luôn được lưu cùng đơn vị với `levels`: lúc dựng chỉ báo, zone/profile.py
nhân mọi mức giá của phiên với `close_kho_nến_DNSE[ngày] / close`, nên hai loại phiên về cùng một thang và sự
kiện chia cổ tức xảy ra SAU khi lưu vẫn tự đúng.

Phiên tick thật luôn thắng phiên ước lượng cùng ngày; phiên thật đã có thì không ghi đè (idempotent).
Giữ tối đa MAX_SESSIONS phiên gần nhất (cửa sổ lớn nhất 40 + dự trữ).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from common.config import ROOT, TZ

logger = logging.getLogger(__name__)

ZONE_DATA = ROOT / "data" / "zone"
MAX_SESSIONS = 70


def path(symbol: str, base: Path = ZONE_DATA) -> Path:
    return base / f"{symbol.upper()}.json"


def load(symbol: str, base: Path = ZONE_DATA) -> dict:
    try:
        d = json.loads(path(symbol, base).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"symbol": symbol.upper(), "updated_at": "", "sessions": {}}
    d.setdefault("sessions", {})
    return d


def save(store: dict, base: Path = ZONE_DATA) -> None:
    store["updated_at"] = datetime.now(TZ).isoformat(timespec="seconds")
    keep = sorted(store["sessions"])[-MAX_SESSIONS:]
    store["sessions"] = {k: store["sessions"][k] for k in keep}
    p = path(store["symbol"], base)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(store, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def has_real(store: dict, day: str) -> bool:
    s = store["sessions"].get(day)
    return bool(s) and not s.get("est", False)


def put(store: dict, day: str, session: dict) -> bool:
    """Ghi phiên vào kho. Trả False nếu bỏ qua: đã có phiên thật ngày đó, hoặc phiên mới là ước lượng mà kho đã có gì."""
    cur = store["sessions"].get(day)
    if cur is not None and (not cur.get("est", False) or session.get("est", False)):
        return False
    store["sessions"][day] = session
    return True


def recent(store: dict, n: int) -> list[tuple[str, dict]]:
    """n phiên gần nhất, CŨ → MỚI, dạng (ngày, session)."""
    days = sorted(store["sessions"])[-n:]
    return [(d, store["sessions"][d]) for d in days]
