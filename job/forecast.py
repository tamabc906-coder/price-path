"""Lõi dự báo hằng ngày: kho nến → đặc trưng → ô chế độ → pool → nón (bootstrap) → sửa cỡ (conformal) →
2 kịch bản → P(tăng) = tần suất ô (LightGBM chỉ khi cổng bật). Lớp SỰ KIỆN (model/events.py): mã có sự kiện đạt
cổng E1 trong 10 phiên gần nhất mang nón lịch sử sau sự kiện — thứ duy nhất đo ra có hướng; chuông mặc định theo
sự kiện (alert_mode="events"), luật P(tăng) cũ chỉ chạy khi alert_mode="p10". Kèm bước CHẤM ĐIỂM: nón phát h phiên trước
đến hạn hôm nay → tỷ lệ mã trúng → cập nhật hệ số giãn. Tách khỏi run_daily để test được bằng kho giả.

Pool dựng lại mỗi ngày từ toàn bộ kho: hàng nào có đủ 20 phiên sau mới vào pool, nên pool tự động chỉ chứa
quá khứ ≥ 20 phiên trước hôm nay — không nhìn tương lai.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from common import store as store_mod
from common.config import ARTIFACTS, INDEX_SYMBOL
from model import cone, conformal, direction, events, regime
from model.features import PATH_COLS, build_all

log = logging.getLogger(__name__)

HS = cone.HS
QS = cone.QS
CONF_STATE = ARTIFACTS / "conformal_state.json"
COVER_WINDOW = 60          # cửa sổ chấm "đúng cỡ" (đo: 20 phiên dao động quá mạnh với 39 mã tương quan)
COVER_BAND = 0.06          # ±6 điểm quanh mục tiêu
EVENTS_STATS = ARTIFACTS / "events_stats.json"      # scripts/measure_events.py --md ghi (cổng + hệ số nới nón)
EVENT_ACTIVE = 10          # sự kiện còn hiện 10 phiên kể từ ngày xảy ra (= kỳ hạn đo +10p)
EVENT_MIN_POOL = 30


def load_conf_state() -> dict:
    try:
        return json.loads(CONF_STATE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return conformal.new_state(HS)


def save_conf_state(state: dict) -> None:
    CONF_STATE.parent.mkdir(parents=True, exist_ok=True)
    CONF_STATE.write_text(json.dumps(state, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def load_event_stats() -> dict:
    try:
        return json.loads(EVENTS_STATS.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"events": {}}


def enabled_events(cfg: dict, stats: dict) -> list[str]:
    """settings.events_enabled nếu có, ngược lại các sự kiện ĐẠT cổng E1."""
    en = cfg.get("events_enabled")
    if en is None:
        en = [k for k, v in (stats.get("events") or {}).items() if v.get("pass")]
    return [k for k in events.CODES if k in en]


def event_setup(store: dict, f: pd.DataFrame, syms: list[str]) -> dict:
    """Cột sự kiện của mọi mã ghép với (c, vol20, đường 20 phiên sau) + pool đường đi sau mỗi loại sự kiện.
    Pool chỉ gồm hàng có đủ 20 phiên sau → tự động là quá khứ ≥ 20 phiên, không nhìn tương lai."""
    parts = []
    for sym in syms:
        b = store_mod.bars(store, sym)
        if len(b) < 60:
            continue
        e = events.detect(b)
        e.insert(0, "symbol", sym)
        parts.append(e)
    if not parts:
        return {"frame": pd.DataFrame(), "pools": {}}
    g = f[["symbol", "d", "c", "vol20", *PATH_COLS]].merge(pd.concat(parts, ignore_index=True), on=["symbol", "d"], how="left")
    for k in events.CODES:
        g[k] = g[k].fillna(False).astype(bool)
    ok = g[PATH_COLS].notna().all(axis=1) & (g["vol20"] > 0)
    return {"frame": g, "pools": {k: events.pool_steps(g[ok & g[k]]) for k in events.CODES}}


def symbol_events(g: pd.DataFrame, sym: str, td: str, codes: list[str], pools: dict, stats: dict, n_sim: int) -> list[dict]:
    """Sự kiện đang bật của một mã trong EVENT_ACTIVE phiên gần nhất (≤ td), mỗi cái kèm nón neo tại ngày sự kiện."""
    if g.empty or not codes:
        return []
    gs = g[(g["symbol"] == sym) & (g["d"] <= pd.Timestamp(td))].tail(EVENT_ACTIVE + 1).reset_index(drop=True)
    last, out = len(gs) - 1, []
    for i, row in gs.iterrows():
        for k in codes:
            if not row[k]:
                continue
            day = row["d"].date().isoformat()
            price0, vol0 = float(row["c"]), float(row["vol20"])
            st = (stats.get("events") or {}).get(k, {})
            ev = {"code": k, "name": events.NAMES[k], "date": day, "age": int(last - i), "price0": round(price0, 2),
                  "path": [round(float(x), 2) for x in gs["c"].iloc[i:]],
                  "stats": {x: st.get(x) for x in ("ex10", "ret10", "win10", "years_win", "years", "n", "cov80")},
                  "n_pool": int(len(pools.get(k, ()))), "q": None, "q_log": None, "p_touch": None}
            pool = pools.get(k)
            if pool is not None and len(pool) >= EVENT_MIN_POOL and vol0 > 0:
                paths = cone.simulate(vol0, pool, n=n_sim, seed=cone.seed_for(sym, day))
                raw = _q_log_dict(cone.quantiles_batch(paths[None, ...])[0])
                q_log = {h: {str(q): v for q, v in events.widen({int(q): v for q, v in d.items()}, st.get("scale")).items()}
                         for h, d in raw.items()}
                ev.update(q_log=q_log, q=_to_prices(q_log, price0), p_touch=round(events.touch_prob(paths), 3))
            out.append(ev)
    return out


def calendar(store: dict) -> list[str]:
    """Lịch phiên = hợp các ngày có nến trong kho (ISO, tăng dần)."""
    days: set[str] = set()
    for rows in store["bars"].values():
        days.update(r[0] for r in rows)
    return sorted(days)


def _q_log_dict(qb: np.ndarray) -> dict[str, dict[str, float]]:
    return {str(h): {str(q): float(qb[i, j]) for j, q in enumerate(QS)} for i, h in enumerate(HS)}


def _to_prices(q_log: dict[str, dict[str, float]], price: float) -> dict[str, dict[str, float]]:
    return {h: {q: round(price * math.exp(v), 2) for q, v in d.items()} for h, d in q_log.items()}


def forecast_all(store: dict, items: list[dict], trade_date: date, cfg: dict, conf_state: dict,
                 n_sim: int = cone.N_SIM) -> tuple[list[dict], list[dict], dict]:
    """(dự báo từng mã, mã nến cũ, thông tin pool). Mã có nến cuối < trade_date → stale, không dự báo."""
    syms = sorted(it["symbol"] for it in items)
    f = build_all(store, syms, INDEX_SYMBOL, store_mod.bars)
    keys = regime.keys_for(f)
    pools = regime.build_pools(f, keys)
    ev = event_setup(store, f, syms)
    return forecast_from(f, keys, pools, items, trade_date, cfg, conf_state, n_sim, ev=ev)


def forecast_from(f, keys, pools: dict, items: list[dict], trade_date: date, cfg: dict, conf_state: dict,
                  n_sim: int = cone.N_SIM, ev: dict | None = None) -> tuple[list[dict], list[dict], dict]:
    """Bản dùng đặc trưng/pool đã dựng sẵn (scripts/backfill.py gọi nhiều ngày liên tiếp).
    f phải chỉ chứa hàng có ngày ≤ trade_date; pools phải dựng từ hàng có t+20 ≤ trade_date.
    ev = event_setup(...) hoặc None (không tính sự kiện)."""
    syms = sorted(it["symbol"] for it in items)
    names = {it["symbol"]: it.get("company_name") or it.get("name") or "" for it in items}
    glob = pools.get((), np.zeros((0, 20), np.float32))
    gate = direction.load_gate()
    boosters = {h: direction.load_booster(h) for h in (5, 10)} if gate.get("enabled") else {}
    if gate.get("enabled") and not all(boosters.values()):
        log.warning("gate bật nhưng thiếu booster/lightgbm — dùng tần suất ô")
        boosters = {}
    td = trade_date.isoformat()
    ev_stats = load_event_stats()
    ev_codes = enabled_events(cfg, ev_stats) if ev else []
    ev_push = set(cfg.get("events_push") or [])
    mode = cfg.get("alert_mode", "events")
    out, stale = [], []
    for sym in syms:
        g = f[f["symbol"] == sym]
        if g.empty:
            continue
        last = g.iloc[-1]
        last_d = last["d"].date().isoformat()
        if last_d != td:
            stale.append({"symbol": sym, "last_date": last_d})
            continue
        key = keys.loc[last.name]
        price = float(last["c"])
        prev = g["c"].iloc[-2] if len(g) > 1 else None
        chg = round((price / prev - 1) * 100, 2) if prev else None
        if key is None or not (last["vol20"] > 0):
            out.append({"symbol": sym, "name": names[sym], "price": price, "change_pct": chg, "ok": False,
                        "reason": "chưa đủ 250 phiên lịch sử để xếp chế độ"})
            continue
        pool, level, n = regime.pool_for(key, pools)
        paths = cone.simulate(float(last["vol20"]), pool, n=n_sim, seed=cone.seed_for(sym, td))
        q_raw = _q_log_dict(cone.quantiles_batch(paths[None, ...])[0])
        q_adj = {str(h): {str(k): v for k, v in conformal.adjust({int(k): v for k, v in q_raw[str(h)].items()}, conf_state, h).items()}
                 for h in HS}
        p5, p10 = regime.freq_up(pool, 5), regime.freq_up(pool, 10)
        p_src = "regime_freq"
        if boosters:
            p5, p10 = float(direction.predict(boosters[5], g.iloc[[-1]])[0]), float(direction.predict(boosters[10], g.iloc[[-1]])[0])
            p_src = "lgbm"
        evs = symbol_events(ev["frame"], sym, td, ev_codes, ev["pools"], ev_stats, n_sim) if ev_codes else []
        alert_events = [e["code"] for e in evs if e["age"] == 0 and e["code"] in ev_push]
        if mode == "p10":
            alert = (p10 >= cfg["p_min"] and n >= cfg["n_min"]
                     and (not cfg.get("require_q25") or q_adj["10"]["25"] > 0))
        else:
            alert = bool(alert_events)
        item = {
            "symbol": sym, "name": names[sym], "price": price, "change_pct": chg, "volume": int(last["v"]), "ok": True,
            "key": list(key), "chips": regime.chips(key), "level": int(level), "n": int(n),
            "vol20": round(float(last["vol20"]), 5),
            "p5": round(p5, 3), "p10": round(p10, 3), "base5": round(regime.freq_up(glob, 5), 3),
            "base10": round(regime.freq_up(glob, 10), 3), "p_src": p_src,
            "q": _to_prices(q_adj, price), "q_log": q_adj,
            "scenarios": cone.scenarios(paths, price, seed=cone.seed_for(sym, td)) if cfg.get("scenarios", True) else [],
            "alert": bool(alert), "alert_events": alert_events, "events": evs,
        }
        out.append(item)
    info = {"rows": int(len(f)), "pool_global": int(len(glob)), "cells_full": sum(1 for k in pools if len(k) == len(regime.AXES)),
            "gate_enabled": bool(gate.get("enabled")), "p_src": "lgbm" if boosters else "regime_freq",
            "events_meta": {"alert_mode": mode, "enabled": ev_codes, "push": [k for k in ev_codes if k in ev_push],
                            "active_days": EVENT_ACTIVE, "generated": ev_stats.get("generated"),
                            "pools": {k: int(len(p)) for k, p in (ev or {}).get("pools", {}).items()},
                            "stats": {k: {x: v.get(x) for x in ("name", "pass", "n", "ex10", "ret10", "win10", "years_win",
                                                                "years", "ex5", "ex20", "cov80", "scale")}
                                      for k, v in (ev_stats.get("events") or {}).items()}}}
    return out, stale, info


def score_matured(store: dict, cal: list[str], trade_date: date, daily_dir: Path, conf_state: dict,
                  scored: set[str]) -> list[dict]:
    """Chấm các nón đã phát 5/10/20 phiên trước (file daily/<ngày>.json) bằng giá đóng cửa hôm nay.
    Một con số mỗi (ngày phát, h, mức) = tỷ lệ mã trúng → conformal.update. `scored` tránh chấm hai lần."""
    td = trade_date.isoformat()
    if td not in cal:
        return []
    i = cal.index(td)
    closes = {sym: {r[0]: r[4] for r in rows} for sym, rows in store["bars"].items()}
    results = []
    for h in HS:
        if i - h < 0:
            continue
        d0 = cal[i - h]
        tag = f"{d0}|{h}"
        fpath = daily_dir / f"{d0}.json"
        if tag in scored or not fpath.exists():
            continue
        try:
            fc = json.loads(fpath.read_text(encoding="utf-8")).get("forecasts") or {}
        except Exception:  # noqa: BLE001
            continue
        hits = {lv: [] for lv in conformal.LEVELS}
        for sym, rec in fc.items():
            c_now = closes.get(sym, {}).get(td)
            q = (rec.get("q_log") or {}).get(str(h))
            if not c_now or not q or not rec.get("price"):
                continue
            realized = math.log(c_now / rec["price"])
            for lv in conformal.LEVELS:
                hits[lv].append(conformal.hit({int(k): v for k, v in q.items()}, realized, lv))
        if not hits[80]:
            continue
        for lv in conformal.LEVELS:
            rate = float(np.mean(hits[lv]))
            s_new = conformal.update(conf_state, h, lv, rate)
            results.append({"date": d0, "h": h, "level": lv, "hit": round(rate, 4), "n": len(hits[lv]), "s": s_new})
        scored.add(tag)
    return results


def verdict(conf_state: dict, h: int = 10, level: int = 80) -> dict:
    """Ô lớn tab Lịch sử: coverage 60 phiên của nón 80 % tại +10 → đúng cỡ / hẹp / rộng / chưa đủ."""
    cov = conformal.coverage(conf_state, h, level, last=COVER_WINDOW)
    n = len(conf_state["levels"][str(h)][str(level)]["hits"])
    target = level / 100
    if cov is None or n < 20:
        status, text = "pending", f"chưa đủ phiên để chấm ({n}/20)"
    elif cov < target - COVER_BAND:
        status, text = "narrow", "Nón đang hẹp — giá thật văng ra ngoài nhiều hơn dự kiến"
    elif cov > target + COVER_BAND:
        status, text = "wide", "Nón đang rộng — bao quá nhiều, đang tự thu hẹp"
    else:
        status, text = "ok", "Nón đang đúng cỡ — tin được"
    return {"status": status, "text": text, "cov": cov, "n": min(n, COVER_WINDOW), "window": COVER_WINDOW,
            "cov20": conformal.coverage(conf_state, h, level, last=20),
            "s": {str(hh): {str(lv): conformal.scale(conf_state, hh, lv) for lv in conformal.LEVELS} for hh in HS}}
