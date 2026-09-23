"""Job sau phiên — GitHub Actions 15:40 T2–T6 (hoặc local: python -m job.run_daily [--dry-run|--no-push|--force]).

Luồng: danh mục KingStock → 30 ngày nến DNSE gần nhất (+ VNINDEX) nối vào kho data/history.json → chấm các nón
đã đến hạn (sửa hệ số giãn) → dự báo nón + P(tăng) + 2 kịch bản cho từng mã (job/forecast.py) → push mã qua
ngưỡng → ghi docs/data/latest.json, bars.json, daily/<ngày>.json, state.json + model/artifacts/conformal_state.json.

Idempotent như candle-radar: có daily/<ngày>.json rồi thì thoát trừ --force. Nguồn chưa chốt (≥ 20 % mã thanh
khoản thiếu nến ATC 14:45) → không ghi gì, chờ cron dự phòng. Mã nến cũ → stale, không dự báo.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime

from common import dnse, store as store_mod
from common.config import HISTORY, INDEX_SYMBOL, SITE_DATA, TZ

from . import forecast, push, settings, watchlist
from model import direction

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("job")

LATEST = SITE_DATA / "latest.json"
BARS = SITE_DATA / "bars.json"
STATE = SITE_DATA / "state.json"
DAILY = SITE_DATA / "daily"

FETCH_DAYS = 30            # lịch sử nằm trong kho; mỗi ngày chỉ lấy đoạn gần nhất để nối
BARS_IN_CHART = 60         # nến mỗi mã cho tab Biểu đồ
LIQUID_MIN_BARS = 30
UNSETTLED_RATIO = 0.2
MAX_SCORES = 400           # bản ghi chấm điểm giữ trong state.json


def _load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def _dump(path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def fetch_bars(tickers: list[str], client=None, days: int = FETCH_DAYS) -> tuple[dict[str, list[dict]], list[str]]:
    """Nến ngày gần nhất cho từng mã + danh sách mã thanh khoản mà nến HÔM NAY chưa chốt.
    Chép nguyên candle-radar/job/run_daily.py::fetch_bars."""
    bars: dict[str, list[dict]] = {}
    voters: list[str] = []
    lacking: list[str] = []
    today = dnse.today_vn()
    with (client or dnse.DnseClient(days=days)) as c:
        for i, t in enumerate(sorted(tickers), 1):
            b = c.daily(t)
            if not b:
                continue
            if b[-1]["d"] == today:
                minutes = c.today_minutes(t)
                if len(minutes) >= LIQUID_MIN_BARS:
                    voters.append(t)
                    if not dnse.session_settled(minutes):
                        lacking.append(t)
                b[-1] = dnse.merge_today(b[-1], minutes)
            bars[t] = b
            if i % 10 == 0:
                log.info("giá: %d/%d mã", i, len(tickers))
    unsettled = lacking if voters and len(lacking) / len(voters) >= UNSETTLED_RATIO else []
    if lacking and not unsettled:
        log.info("Mã thiếu nến ATC nhưng nguồn nhìn chung đã chốt (%d/%d): %s",
                 len(lacking), len(voters), ", ".join(lacking))
    return bars, unsettled


def bars_for_chart(st: dict, syms: list[str], n: int = BARS_IN_CHART) -> dict[str, list[list]]:
    return {sym: st["bars"][sym][-n:] for sym in syms if st["bars"].get(sym)}


def _history(days: int, scores: list[dict]) -> list[dict]:
    """Tab Lịch sử: mỗi phiên số mã báo + coverage 80 % đã chấm cho nón 5/10 phiên phát hôm đó."""
    cov = {}
    for s in scores:
        if s["level"] == 80:
            cov.setdefault(s["date"], {})[str(s["h"])] = s["hit"]
    out = []
    if not DAILY.exists():
        return out
    for f in sorted(DAILY.glob("*.json"), reverse=True)[:days]:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        date = d.get("trade_date") or f.stem
        out.append({"date": date, "n_alerts": len(d.get("alerts") or []), "alerts": d.get("alerts") or [],
                    "cov80": cov.get(date, {}), "late": bool(d.get("late"))})
    return out


def _send_alerts(alerts: list[dict], trade_iso: str, subs: list[dict], digest_threshold: int,
                 alert_mode: str = "events") -> dict:
    res = {"sent": 0, "gone": 0, "failed": 0, "errors": [], "mode": "none", "n_symbols": len(alerts)}
    if not alerts:
        return res
    if len(alerts) > digest_threshold:
        res["mode"] = "digest"
        payloads = [push.digest_payload(alerts, trade_iso, alert_mode)]
    elif alert_mode == "events":
        res["mode"] = "per_event"
        payloads = [push.event_payload(it, ev, trade_iso) for it in alerts
                    for ev in it["events"] if ev["code"] in it["alert_events"] and ev["age"] == 0]
    else:
        res["mode"] = "per_symbol"
        payloads = [push.symbol_payload(it, trade_iso) for it in alerts]
    for p in payloads:
        r = push.send(p, subs)
        for k in ("sent", "gone", "failed"):
            res[k] += r[k]
        res["errors"] += r["errors"]
    return res


def run(force: bool = False, dry_run: bool = False, no_push: bool = False) -> int:
    now = datetime.now(TZ)
    st = _load(STATE, {})
    if not dry_run and not no_push:
        _welcome_new_devices(st, now)
    cfg = settings.load()

    items, wl_source = watchlist.load()
    if not items:
        log.error("Không có danh mục: KingStock không trả lời và chưa có docs/data/watchlist.json")
        st.update({"last_run": now.isoformat(timespec="seconds"), "watchlist_error": "không có danh mục"})
        _dump(STATE, st)
        return 2
    tickers = sorted(it["symbol"] for it in items)
    log.info("Danh mục %d mã (nguồn %s)", len(tickers), wl_source)

    hist = store_mod.load(HISTORY)
    with dnse.DnseClient(days=FETCH_DAYS) as client:
        fetched = store_mod.ensure(hist, items, client)          # mã mới → trọn lịch sử một lần
        if fetched:
            log.info("Tải trọn lịch sử cho mã mới: %s", ", ".join(fetched))
        bars, unsettled = fetch_bars(tickers, client)
        idx_bars = client.index(INDEX_SYMBOL)
    if not bars:
        log.error("DNSE không trả về gì: %s", dnse.last_error)
        st.update({"dnse_error": dnse.last_error, "last_run": now.isoformat(timespec="seconds")})
        _dump(STATE, st)
        return 3
    trade_date = max(b[-1]["d"] for b in bars.values())
    trade_iso = trade_date.isoformat()
    daily_file = DAILY / f"{trade_iso}.json"
    if daily_file.exists() and not force:
        log.info("Đã có %s — không chạy lại (dùng --force nếu muốn)", daily_file.name)
        return 0
    if unsettled and not force:
        msg = (f"Nguồn chưa chốt phiên {trade_iso}: {len(unsettled)}/{len(bars)} mã chưa có nến ATC "
               f"({', '.join(unsettled[:8])}{'…' if len(unsettled) > 8 else ''}) — chờ cron sau")
        log.warning(msg)
        st.update({"last_run": now.isoformat(timespec="seconds"),
                   "unsettled": {"trade_date": trade_iso, "tickers": unsettled, "at": now.isoformat(timespec="seconds")}})
        _dump(STATE, st)
        return 0
    late = bool(st.pop("unsettled", None))
    if (now.date() - trade_date).days > 4:
        log.warning("Phiên gần nhất %s cách hôm nay quá 4 ngày — DNSE có thể chưa cập nhật", trade_iso)

    changed = sum(store_mod.merge(hist, sym, b) for sym, b in bars.items()) + store_mod.merge(hist, INDEX_SYMBOL, idx_bars)
    log.info("Kho: nối %d nến mới/đổi", changed)

    # chấm nón đã đến hạn TRƯỚC khi dự báo → nón hôm nay dùng hệ số giãn đã sửa
    conf_state = forecast.load_conf_state()
    scored = set(st.get("scored") or [])
    cal = forecast.calendar(hist)
    scores = forecast.score_matured(hist, cal, trade_date, DAILY, conf_state, scored)
    for s in scores:
        log.info("chấm %s h=%d mức %d: trúng %.0f %% (%d mã) → s=%.3f", s["date"], s["h"], s["level"], s["hit"] * 100, s["n"], s["s"])

    fc, stale, info = forecast.forecast_all(hist, items, trade_date, cfg, conf_state)
    alerts = [it for it in fc if it.get("ok") and it["alert"]]
    ver = forecast.verdict(conf_state)
    em = info["events_meta"]
    log.info("Phiên %s: %d dự báo, %d mã nến cũ, %d cảnh báo (chế độ %s, sự kiện bật %s, push %s) · pool %s hàng, %d ô đủ trục · %s",
             trade_iso, sum(1 for it in fc if it.get("ok")), len(stale), len(alerts), em["alert_mode"], em["enabled"],
             em["push"], f"{info['pool_global']:,}", info["cells_full"], ver["text"])

    push_res: dict = {"skipped": True}
    if not dry_run and not no_push:
        subs, src = push.subscriptions()
        push_res = {"source": src, "n_devices": len(subs)}
        if subs and push.configured():
            push_res.update(_send_alerts(alerts, trade_iso, subs, int(cfg.get("digest_threshold") or 6), em["alert_mode"]))
            if cfg.get("heartbeat") and now.weekday() == 0:
                push_res["heartbeat"] = push.send(push.heartbeat_payload(ver["cov"], trade_iso), subs)["sent"]
            if push.test_requested():
                push_res["test"] = push.send(push.test_payload(), subs)["sent"]
        elif not push.configured():
            push_res["errors"] = ["Thiếu khoá VAPID"]
        if push_res.get("gone"):
            st["push_gone_at"] = now.isoformat(timespec="seconds")

    all_scores = (st.get("scores") or []) + scores
    all_scores = all_scores[-MAX_SCORES:]
    gate = direction.load_gate()
    latest = {
        "generated_at": now.isoformat(timespec="seconds"), "trade_date": trade_iso,
        "watchlist": {"n": len(tickers), "source": wl_source},
        "source": {"dnse_ok": bool(dnse.last_ok), "dnse_error": dnse.last_error, "n_priced": len(bars),
                   "unsettled": unsettled, "late": late, "history_rows": info["rows"]},
        "settings": {k: v for k, v in cfg.items() if not k.startswith("_")},
        "model": {"pool_global": info["pool_global"], "cells_full": info["cells_full"], "p_src": info["p_src"],
                  "gate": {"enabled": bool(gate.get("enabled")),
                           "per_h": {h: {k: v for k, v in d.items() if k != "rows"} for h, d in (gate.get("per_h") or {}).items()},
                           "rows": {h: d.get("rows", []) for h, d in (gate.get("per_h") or {}).items()},
                           "trained_at": gate.get("trained_at")}},
        "events_meta": em, "verdict": ver, "stale": stale,
        "items": [{k: v for k, v in it.items() if k != "q_log"} for it in fc],
        "alerts": [it["symbol"] for it in alerts], "push": push_res,
    }

    if dry_run:
        print(json.dumps({k: v for k, v in latest.items() if k not in ("items", "model", "settings")}, ensure_ascii=False, indent=1, default=str))
        for it in sorted((x for x in fc if x.get("ok")), key=lambda x: -x["p10"]):
            q = it["q"]["10"]
            print(f"  {'▲' if it['alert'] else ' '} {it['symbol']:<5} {it['price']:>8.2f} P10 {it['p10']:.2f} (mốc {it['base10']:.2f}) "
                  f"nón80 +10p {q['10']:.1f}–{q['90']:.1f} · n={it['n']} cấp {it['level']} · {' · '.join(it['chips'])}")
        for it in fc:
            if not it.get("ok"):
                print(f"  ? {it['symbol']} {it.get('reason')}")
        print(f"Sự kiện (bật {em['enabled']}, push {em['push']}, hiện {em['active_days']} phiên):")
        for it in fc:
            for e in it.get("events") or []:
                q = (e.get("q") or {}).get("10") or {}
                print(f"  {'🔔' if e['code'] in it.get('alert_events', []) else '  '} {it['symbol']:<5} {e['name']} · {e['date']} "
                      f"(cách {e['age']} phiên) · giá lúc đó {e['price0']} → nay {it['price']} · nón80 +10p "
                      f"{q.get('10', '—')}–{q.get('90', '—')} · chạm +5 % trước: {e.get('p_touch')}")
        return 0

    _dump(daily_file, {"trade_date": trade_iso, "generated_at": latest["generated_at"], "late": late,
                       "forecasts": {it["symbol"]: {"price": it["price"], "q_log": it["q_log"], "p10": it["p10"],
                                                    "alert": it["alert"], "level": it["level"], "n": it["n"],
                                                    "events": [{"code": e["code"], "date": e["date"], "age": e["age"],
                                                                "price0": e["price0"],
                                                                "q_log10": (e.get("q_log") or {}).get("10")}
                                                               for e in it.get("events") or []]}
                                     for it in fc if it.get("ok")},
                       "alerts": [it["symbol"] for it in alerts], "stale": stale})
    latest["history"] = _history(int(cfg.get("history_days") or 30), all_scores)
    _dump(LATEST, latest)
    BARS.write_text(json.dumps({"trade_date": trade_iso, "bars": bars_for_chart(hist, tickers)}, ensure_ascii=False,
                               separators=(",", ":")), encoding="utf-8")
    if changed:
        store_mod.save(hist, HISTORY)
    forecast.save_conf_state(conf_state)
    st.update({"last_run": now.isoformat(timespec="seconds"), "last_trade_date": trade_iso,
               "dnse_error": dnse.last_error, "push": push_res, "scores": all_scores, "scored": sorted(scored)[-600:],
               "watchlist": {"n": len(tickers), "source": wl_source}})
    _dump(STATE, st)
    log.info("Xong: %d mã, %d qua ngưỡng, push %s", len(fc), len(alerts), push_res)
    return 0


def _welcome_new_devices(st: dict, now: datetime) -> None:
    """Máy mới đăng ký → gửi ngay một thông báo chào mừng, TRƯỚC bước idempotent. Chép từ candle-radar."""
    subs, src = push.subscriptions()
    st["devices"] = {"n": len(subs), "source": src, "vapid": push.configured(), "checked_at": now.isoformat(timespec="seconds")}
    if not subs or not push.configured():
        _dump(STATE, st)
        return
    known = set(st.get("known_subs") or [])
    new = [s for s in subs if push._sub_id(s) not in known]
    if new:
        payload = {"kind": "welcome", "title": "Đã kết nối — máy này sẽ nhận thông báo",
                   "body": "Nón xác suất + P(tăng) sau phiên 15:40 các ngày T2–T6; chỉ báo mã qua ngưỡng.",
                   "url": "./#today", "tag": "pp-welcome"}
        r = push.send(payload, new)
        log.info("Chào mừng %d máy mới (nguồn %s): %s", len(new), src, r)
        st["welcome"] = {"at": now.isoformat(timespec="seconds"), **r}
    st["known_subs"] = sorted(known | {push._sub_id(s) for s in subs})
    _dump(STATE, st)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="chạy lại dù hôm nay đã có file")
    ap.add_argument("--dry-run", action="store_true", help="in kết quả, không ghi file, không push")
    ap.add_argument("--no-push", action="store_true", help="ghi file nhưng không gửi thông báo")
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(run(force=a.force, dry_run=a.dry_run, no_push=a.no_push))


if __name__ == "__main__":
    main()
