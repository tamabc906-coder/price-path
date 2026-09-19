"""Cài đặt: docs/data/settings.json (commit trong repo) → Cloudflare Worker KV nếu có → mặc định trong code.
Chép khuôn candle-radar/job/settings.py, đổi DEFAULTS cho ngưỡng chuông của nón."""
from __future__ import annotations

import json
import logging

import httpx

from common.config import HTTP_TIMEOUT, SITE_DATA, WORKER_TOKEN, WORKER_URL

logger = logging.getLogger(__name__)

DEFAULTS = {
    "p_min": 0.58,             # P(tăng 10p) tối thiểu để báo (đo: chỉ ~15 % hàng đạt; 0,60 → 8,5 %)
    "n_min": 200,              # ô chế độ phải có ≥ ngần này mẫu lịch sử mới đáng báo
    "require_q25": False,      # thêm điều kiện phân vị 25 % tại +10 phiên > giá hôm nay (rất hiếm)
    "digest_threshold": 6,     # quá số mã này → một thông báo tổng hợp
    "heartbeat": False,        # nhịp tim thứ Hai
    "history_days": 30,        # số phiên hiện ở tab Lịch sử
    "scenarios": True,         # tính 2 kịch bản A/B
}

LOCAL = SITE_DATA / "settings.json"


def load() -> dict:
    s = dict(DEFAULTS)
    if LOCAL.exists():
        try:
            s.update(json.loads(LOCAL.read_text(encoding="utf-8")))
        except Exception as exc:  # noqa: BLE001
            logger.warning("settings.json hỏng: %s", exc)
    if WORKER_URL and WORKER_TOKEN:
        try:
            r = httpx.get(f"{WORKER_URL}/settings", headers={"Authorization": f"Bearer {WORKER_TOKEN}"},
                          timeout=HTTP_TIMEOUT)
            if r.status_code == 200 and r.text.strip():
                s.update(r.json())
                s["_source"] = "worker"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Worker /settings không trả lời: %s — dùng bản local", exc)
    s["p_min"] = float(s.get("p_min") or DEFAULTS["p_min"])
    s["n_min"] = int(s.get("n_min") or DEFAULTS["n_min"])
    return s
