"""Web Push qua pywebpush + VAPID. Chép từ candle-radar/job/push.py, đổi payload cho nón xác suất.
Nguồn địa chỉ: Worker KV (GET /subs) → fallback PUSH_SUBS_FALLBACK (JSON trong Secret).

- configured() đòi CẢ HAI khoá: thiếu public key thì lỗi im lặng (bài học KingStock).
- 404/410 = trình duyệt đã huỷ đăng ký → báo Worker xoá và ghi vào state để giao diện hiện dòng đỏ.
"""
from __future__ import annotations

import hashlib
import json
import logging

import httpx
from pywebpush import WebPushException, webpush

from common.config import (
    HTTP_TIMEOUT, PUSH_SUBS_FALLBACK, VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, VAPID_SUBJECT,
    WORKER_TOKEN, WORKER_URL,
)

logger = logging.getLogger(__name__)
TTL_ALERT = 16 * 3600


def configured() -> bool:
    return bool(VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY)


def _worker_headers() -> dict:
    return {"Authorization": f"Bearer {WORKER_TOKEN}"}


def subscriptions() -> tuple[list[dict], str]:
    """(danh sách subscription, nguồn). Worker trước, fallback sau."""
    if WORKER_URL and WORKER_TOKEN:
        try:
            r = httpx.get(f"{WORKER_URL}/subs", headers=_worker_headers(), timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            subs = r.json()
            if isinstance(subs, dict):
                subs = list(subs.values())
            return subs, "worker"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Worker /subs lỗi: %s — dùng fallback", exc)
    if PUSH_SUBS_FALLBACK.strip():
        try:
            subs = json.loads(PUSH_SUBS_FALLBACK)
            return (subs if isinstance(subs, list) else [subs]), "fallback"
        except json.JSONDecodeError as exc:
            logger.error("PUSH_SUBS_FALLBACK không phải JSON: %s", exc)
    return [], "none"


def test_requested() -> bool:
    if not (WORKER_URL and WORKER_TOKEN):
        return False
    try:
        r = httpx.get(f"{WORKER_URL}/test", headers=_worker_headers(), timeout=HTTP_TIMEOUT)
        return bool(r.status_code == 200 and r.json().get("requested"))
    except Exception:  # noqa: BLE001
        return False


def _sub_id(sub: dict) -> str:
    return hashlib.sha256(sub["endpoint"].encode()).hexdigest()[:16]


def _forget(sub: dict) -> None:
    if WORKER_URL and WORKER_TOKEN:
        try:
            httpx.delete(f"{WORKER_URL}/subs/{_sub_id(sub)}", headers=_worker_headers(), timeout=HTTP_TIMEOUT)
        except Exception:  # noqa: BLE001
            pass


def send(payload: dict, subs: list[dict]) -> dict:
    """Gửi một payload tới mọi thiết bị. Trả về {sent, gone, failed, errors}."""
    res = {"sent": 0, "gone": 0, "failed": 0, "errors": []}
    if not configured():
        res["errors"].append("Thiếu VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY")
        return res
    data = json.dumps(payload, ensure_ascii=False)
    for sub in subs:
        try:
            webpush(
                subscription_info={"endpoint": sub["endpoint"], "keys": sub["keys"]},
                data=data, ttl=TTL_ALERT,
                vapid_private_key=VAPID_PRIVATE_KEY, vapid_claims={"sub": VAPID_SUBJECT},
                headers={"Urgency": "high"},
            )
            res["sent"] += 1
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (404, 410):
                res["gone"] += 1
                _forget(sub)
            else:
                res["failed"] += 1
                res["errors"].append(f"{_sub_id(sub)}: {status} {exc}"[:200])
        except Exception as exc:  # noqa: BLE001
            res["failed"] += 1
            res["errors"].append(f"{_sub_id(sub)}: {exc}"[:200])
    return res


def _dm(trade_date: str) -> str:
    return f"{trade_date[8:10]}/{trade_date[5:7]}"


def symbol_payload(item: dict, trade_date: str) -> dict:
    """Một thông báo cho MỘT mã qua ngưỡng: P(tăng 10p) + nón 80 % tại +10 phiên."""
    q10 = item["q"]["10"]
    body = (f"giá {item['price']:.2f} · nón 80 % (+10p): {q10['10']:.1f} – {q10['90']:.1f} · "
            f"{' · '.join(item['chips'][:3])} · n={item['n']}")
    return {
        "kind": "cone", "title": f"▲ {item['symbol']} · P(tăng 10p) {round(item['p10'] * 100)} % · phiên {_dm(trade_date)}",
        "body": body, "symbol": item["symbol"], "url": "./#today", "tag": f"pp-{item['symbol']}", "hot": True,
    }


def _pc(x) -> str:
    return "—" if x is None else f"{x * 100:+.1f} %".replace(".", ",")


def event_payload(item: dict, ev: dict, trade_date: str) -> dict:
    """Một thông báo cho MỘT sự kiện mới hôm nay: số lịch sử của sự kiện + nón sự kiện 80 % tại +10 phiên."""
    st = ev.get("stats") or {}
    bits = [f"giá {item['price']:.2f}", f"lịch sử vượt mốc {_pc(st.get('ex10'))}/10p, đúng {st.get('years_win')}/{st.get('years')} năm"]
    q10 = (ev.get("q") or {}).get("10")
    if q10:
        bits.append(f"nón 80 % (+10p): {q10['10']:.1f} – {q10['90']:.1f}")
    if ev.get("p_touch") is not None:
        bits.append(f"chạm +5 % trước −5 %: {round(ev['p_touch'] * 100)} %")
    return {
        "kind": "event", "title": f"▲ {item['symbol']} · {ev['name']} · phiên {_dm(trade_date)}",
        "body": " · ".join(bits), "symbol": item["symbol"], "event": ev["code"], "url": "./#today",
        "tag": f"pp-ev-{item['symbol']}", "hot": True,
    }


def digest_payload(items: list[dict], trade_date: str, mode: str = "p10") -> dict:
    if mode == "events":
        parts = [f"{it['symbol']} ({', '.join(e['name'] for e in it['events'] if e['code'] in it.get('alert_events', []))})"
                 for it in items]
        title = f"{len(items)} mã có sự kiện · phiên {_dm(trade_date)}"
    else:
        parts = [f"{it['symbol']} {round(it['p10'] * 100)} %" for it in items]
        title = f"{len(items)} mã qua ngưỡng P(tăng) · phiên {_dm(trade_date)}"
    return {"kind": "digest", "title": title, "body": " · ".join(parts), "url": "./#today", "tag": "pp-digest", "hot": True}


def heartbeat_payload(cov80: float | None, trade_date: str) -> dict:
    cov = f"nón 80 % bao {round(cov80 * 100)} % (60 phiên)" if cov80 is not None else "chưa đủ phiên để chấm"
    return {"kind": "heartbeat", "title": "Price Path vẫn chạy", "body": f"{cov} · dữ liệu đến phiên {_dm(trade_date)}",
            "url": "./#history", "tag": "pp-heartbeat", "hot": False}


def test_payload() -> dict:
    return {"kind": "test", "title": "Thông báo thử — máy này đã nhận được",
            "body": "Sau phiên, khi có mã phá VAH/VAL có cá mập cùng chiều hoặc cá mập mua/bán dồn về cùng một giá, thẻ như thế này sẽ hiện kể cả khi app đang đóng.",
            "url": "./#today", "tag": "pp-test"}


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    subs, src = subscriptions()
    print(f"{len(subs)} thiết bị (nguồn: {src}) · VAPID {'OK' if configured() else 'THIẾU'}")
    if "--test" in sys.argv:
        print(send(test_payload(), subs))
