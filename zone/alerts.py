"""Thông báo điện thoại theo vùng giá + lệnh cá mập (người dùng chốt 25/09/2026, thay push sự kiện gap-fill).

Một mã được báo ở phiên `day` khi đạt MỤC 1 hoặc MỤC 2 (hoặc cả hai), xét ở từng khung cfg["windows"] (10/20/40):

1. Phá vỡ Value Area có cá mập xác nhận — VAH/VAL lấy từ profile của khung KẾT THÚC Ở PHIÊN TRƯỚC `day`
   (vùng đã có sẵn, không gồm hôm nay):
     phá lên   close hôm qua ≤ VAH < close hôm nay  và  ròng lệnh lớn hôm nay > 0
     thủng     close hôm qua ≥ VAL > close hôm nay  và  ròng lệnh lớn hôm nay < 0
   Phiên ước lượng (nến 1') không có lệnh lớn → không bao giờ đạt mục 1.
2. Cá mập dồn về cùng một giá — giá mua chủ động lớn nhất và giá bán chủ động lớn nhất của lệnh lớn
   (profile.top["big_buy"/"big_sell"][0]) cách nhau ≤ whale_gap (nghìn đồng), CHỈ khi MỚI xuất hiện: khung kết thúc
   ở `day` đạt mà khung kết thúc ở phiên trước chưa đạt (đo 25/09: 19/39 mã đạt liên tục nhiều ngày).

Đã báo người dùng: lab 24/09 đo VAH/VAL không giữ/cản giá hơn mức giả; đây là thống kê mô tả, họ vẫn chọn bật.
"""
from __future__ import annotations

import logging

from . import profile, store

logger = logging.getLogger(__name__)


def _rows(st: dict, days: list[str], closes: dict[str, float]) -> list[tuple[str, dict, float]]:
    return [(d, st["sessions"][d], profile.adjust_factor(st["sessions"][d], closes.get(d))) for d in days]


def _whale_pair(p: dict | None, gap: float) -> tuple[float, float] | None:
    top = (p or {}).get("top") or {}
    b, s = top.get("big_buy") or [], top.get("big_sell") or []
    if b and s and abs(b[0]["p"] - s[0]["p"]) <= gap + 1e-9:
        return b[0]["p"], s[0]["p"]
    return None


def evaluate(symbol: str, st: dict, closes: dict[str, float], day: str, cfg: dict) -> dict | None:
    """Cảnh báo của một mã tại phiên `day`; None nếu không đạt mục nào."""
    days = sorted(d for d in st["sessions"] if d <= day)
    if len(days) < 2 or days[-1] != day:
        return None
    prev = days[-2]
    c, pc = closes.get(day), closes.get(prev)
    big_net = profile.session_stats(day, st["sessions"][day])["big_net_val"]
    gap = float(cfg.get("whale_gap", 0.3))
    breaks, whale = [], []
    for w in cfg["windows"]:
        w = int(w)
        before = profile.build(_rows(st, days[:-1][-w:], closes), cfg)
        if before and c is not None and pc is not None and big_net:
            vah = round(before["bins"][before["va"][1]][0] + before["bin"], 4)
            val = round(before["bins"][before["va"][0]][0], 4)
            if pc <= vah < c and big_net > 0:
                breaks.append({"w": w, "dir": "up", "level": vah})
            elif pc >= val > c and big_net < 0:
                breaks.append({"w": w, "dir": "down", "level": val})
        now = _whale_pair(profile.build(_rows(st, days[-w:], closes), cfg), gap)
        if now and not _whale_pair(before, gap):
            whale.append({"w": w, "buy_p": now[0], "sell_p": now[1]})
    if not breaks and not whale:
        return None
    return {"symbol": symbol, "day": day, "close": c, "big_net_val": big_net, "breaks": breaks, "whale": whale}


def evaluate_all(symbols: list[str], closes_by: dict[str, dict[str, float]], day: str, cfg: dict) -> list[dict]:
    out = []
    for sym in symbols:
        st = store.load(sym)
        if day not in st["sessions"]:
            continue
        a = evaluate(sym, st, closes_by.get(sym, {}), day, cfg)
        if a:
            out.append(a)
    return out


# ---------------------------------------------------------------- nội dung thông báo

def _dm(d: str) -> str:
    return f"{d[8:10]}/{d[5:7]}"


def _px(v: float) -> str:
    return f"{v:.2f}".replace(".", ",")


def _bil(v: float | None) -> str:
    return "—" if v is None else f"{v:+.1f} tỷ".replace(".", ",").replace("-", "−")


def _wins(items: list[dict], direction: str) -> str:
    return ", ".join(f"{b['w']}p" for b in items if b["dir"] == direction)


def headline(a: dict) -> str:
    """Phần sau mã: 'phá VAH 10p, 20p' / 'thủng VAL 20p' / 'cá mập dồn giá 33,00 – 33,05'."""
    bits = []
    if up := _wins(a["breaks"], "up"):
        bits.append(f"phá VAH {up}")
    if dn := _wins(a["breaks"], "down"):
        bits.append(f"thủng VAL {dn}")
    if a["whale"]:
        wz = a["whale"][0]
        lo, hi = sorted((wz["buy_p"], wz["sell_p"]))
        bits.append(f"cá mập dồn giá {_px(lo)}" + (f" – {_px(hi)}" if hi != lo else ""))
    return " · ".join(bits)


def symbol_payload(a: dict) -> dict:
    up = any(b["dir"] == "up" for b in a["breaks"])
    dn = any(b["dir"] == "down" for b in a["breaks"])
    icon = "▲" if up and not dn else "▼" if dn and not up else "⇄"
    body = [f"giá {_px(a['close'])}" if a["close"] is not None else ""]
    for b in a["breaks"]:
        body.append(f"{'VAH' if b['dir'] == 'up' else 'VAL'} {b['w']}p {_px(b['level'])}")
    if a["breaks"]:
        body.append(f"cá mập ròng {_bil(a['big_net_val'])}")
    if a["whale"]:
        wz = a["whale"][0]
        body.append(f"cá mập mua nhiều nhất {_px(wz['buy_p'])}, bán nhiều nhất {_px(wz['sell_p'])} "
                    f"({', '.join(str(x['w']) + 'p' for x in a['whale'])})")
    return {
        "kind": "zone", "title": f"{icon} {a['symbol']} · {headline(a)} · phiên {_dm(a['day'])}",
        "body": " · ".join(x for x in body if x), "symbol": a["symbol"], "url": "./#zone",
        "tag": f"pp-zone-{a['symbol']}", "hot": True,
    }


def digest_payload(items: list[dict], day: str) -> dict:
    ups = [a["symbol"] for a in items if any(b["dir"] == "up" for b in a["breaks"])]
    dns = [a["symbol"] for a in items if any(b["dir"] == "down" for b in a["breaks"])]
    wh = [a["symbol"] for a in items if a["whale"]]
    parts = []
    if ups:
        parts.append("Phá VAH: " + ", ".join(ups))
    if dns:
        parts.append("Thủng VAL: " + ", ".join(dns))
    if wh:
        parts.append("Cá mập dồn giá: " + ", ".join(wh))
    return {"kind": "zone-digest", "title": f"{len(items)} mã vùng giá · phiên {_dm(day)}",
            "body": " · ".join(parts), "url": "./#zone", "tag": "pp-zone-digest", "hot": True}


def payloads(items: list[dict], day: str, digest_over: int) -> list[dict]:
    if not items:
        return []
    if len(items) > digest_over:
        return [digest_payload(items, day)]
    return [symbol_payload(a) for a in items]


def send(items: list[dict], day: str, digest_over: int) -> dict:
    """Gửi qua job/push (VAPID + danh sách máy). Không có máy/khoá → trả lý do, không ném lỗi."""
    from job import push   # import muộn: test hàm thuần không cần pywebpush
    res: dict = {"n_symbols": len(items), "sent": 0, "gone": 0, "failed": 0, "errors": []}
    msgs = payloads(items, day, digest_over)
    res["mode"] = "none" if not msgs else "digest" if len(msgs) == 1 and len(items) > digest_over else "per_symbol"
    if not msgs:
        return res
    subs, src = push.subscriptions()
    res.update({"source": src, "n_devices": len(subs)})
    if not subs or not push.configured():
        res["errors"].append("không có máy đăng ký" if not subs else "thiếu VAPID")
        return res
    for p in msgs:
        r = push.send(p, subs)
        for k in ("sent", "gone", "failed"):
            res[k] += r[k]
        res["errors"] += r["errors"]
    return res
