"""Job vùng giá — GitHub Actions 15:50 T2–T6 (+ dự phòng 16:25, 18:30 và 08:15 sáng hôm sau), hoặc local:
`python -m zone.run_daily [--force] [--dry-run] [FPT HPG]`.

Luồng: danh mục KingStock → với từng mã: phiên gần nhất trên VNDirect (3 lần gọi) → gộp theo mức giá →
data/zone/<MÃ>.json (mã mới chưa có kho → dựng tạm 47 phiên từ nến 1' DNSE trước) → dựng profile 10/20/40 phiên
với hệ số điều chỉnh từ data/history.json → docs/data/zone/latest.json + state.json.

Idempotent theo (mã, ngày): mã đã có phiên thật của ngày giao dịch gần nhất (theo kho nến) thì không gọi
nguồn. Không mã nào mới và không --force → không ghi gì (tránh commit rác mỗi cron dự phòng).
Chạy độc lập với job/run_daily.py: không push, không đụng docs/data/latest.json.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime

from common import dnse, store as hist
from common.config import SITE_DATA, TZ
from common.vndirect import VndirectClient
from common import vndirect
from job import watchlist

from . import backfill, collect, profile, store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("zone.job")

ZONE_SITE = SITE_DATA / "zone"
LATEST = ZONE_SITE / "latest.json"
STATE = ZONE_SITE / "state.json"
SETTINGS = ZONE_SITE / "settings.json"


def _load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def _dump(path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def settings() -> dict:
    return dict(profile.DEFAULT_SETTINGS, **_load(SETTINGS, {}))


def closes_of(h: dict, symbol: str) -> dict[str, float]:
    return {r[0]: float(r[4]) for r in h["bars"].get(symbol, [])}


def volumes_of(h: dict, symbol: str) -> dict[str, int]:
    return {r[0]: int(r[5]) for r in h["bars"].get(symbol, [])}


def build_symbol(st: dict, closes: dict[str, float], cfg: dict) -> dict:
    """Profile cho từng cửa sổ của một mã, mức giá đã về thang điều chỉnh hiện hành."""
    price = None
    price_date = ""
    if closes:
        price_date = max(closes)
        price = closes[price_date]
    out = {"price": price, "price_date": price_date, "profiles": {}}
    for w in cfg["windows"]:
        rows = [(d, s, profile.adjust_factor(s, closes.get(d))) for d, s in store.recent(st, int(w))]
        p = profile.build(rows, cfg)
        if p is not None:
            p["factors"] = sum(1 for _, _, f in rows if f != 1.0)
            out["profiles"][str(w)] = profile.with_distance(p, price)
    return out


def run(force: bool = False, dry_run: bool = False, only: list[str] | None = None) -> int:
    now = datetime.now(TZ)
    cfg = settings()
    items, src = watchlist.load()
    if not items:
        log.error("Không có danh mục (KingStock chết và không có bản chụp)")
        return 2
    if only:
        items = [it for it in items if it["symbol"] in only]
    h = hist.load()
    collected, skipped, failed, warnings = [], [], [], []

    with VndirectClient() as vc, dnse.DnseClient() as dc:
        for it in items:
            sym = it["symbol"]
            st = store.load(sym)
            if not st["sessions"]:
                w, _ = backfill.backfill_symbol(dc, sym, it.get("exchange") or "HOSE", backfill.DEFAULT_DAYS)
                log.info("%s: kho trống, dựng tạm %d phiên từ nến 1'", sym, w)
                st = store.load(sym)
            closes = closes_of(h, sym)
            target = max(closes) if closes else ""
            if target and store.has_real(st, target) and not force:
                skipped.append(sym)
                continue
            got = collect.collect(vc, sym, int(cfg["big_lot_value_vnd"]))
            if got is None:
                failed.append(sym)
                continue
            day, sess = got
            warn = collect.check_volume(sess, volumes_of(h, sym).get(day))
            if warn:
                warnings.append(f"{sym} {day}: {warn}")
                log.warning("%s %s: %s", sym, day, warn)
            if sess.get("gap"):
                warnings.append(f"{sym} {day}: nguồn thiếu {sess['gap']:,} cp tick (vẫn nhận phiên)")
            if store.put(st, day, sess) or force:
                if force:
                    st["sessions"][day] = sess
                if not dry_run:
                    store.save(st)
                collected.append(f"{sym}@{day}")
                log.info("%s: ghi phiên thật %s (%s tick, %s cp)", sym, day, f"{sess['ticks']:,}", f"{sess['total']:,}")
            else:
                skipped.append(sym)

    if not collected and not force:
        # Kho đã có phiên mới hơn bản đã publish thì vẫn phải dựng lại: một lượt trước đó có thể đã ghi
        # data/zone/*.json rồi chết trước khi ghi latest.json, và vì has_real() đã True nên mọi lượt sau
        # đều "bỏ qua" hết — latest.json sẽ đứng mãi ở phiên cũ.
        published = _load(LATEST, {}).get("trade_date", "")
        stored = max((max(store.load(it["symbol"])["sessions"], default="") for it in items), default="")
        if stored <= published:
            # Không ghi cả state.json: workflow commit mọi thay đổi trong docs/data/zone/, ghi là đẻ commit rác.
            log.info("Không có phiên mới (bỏ qua %d, lỗi %d) — không ghi gì", len(skipped), len(failed))
            return 0 if not failed else 1
        log.warning("latest.json đang ở phiên %s nhưng kho đã có %s — dựng lại", published or "—", stored)

    symbols = {}
    trade_date = ""
    for it in items:
        sym = it["symbol"]
        st = store.load(sym)
        if not st["sessions"]:
            continue
        data = build_symbol(st, closes_of(h, sym), cfg)
        data["name"] = it.get("company_name") or ""
        data["exchange"] = it.get("exchange") or ""
        data["last_session"] = max(st["sessions"])
        data["real_sessions"] = sum(1 for s in st["sessions"].values() if not s.get("est", False))
        symbols[sym] = data
        trade_date = max(trade_date, data["last_session"])
    latest = {
        "updated_at": now.isoformat(timespec="seconds"),
        "trade_date": trade_date,
        "settings": cfg,
        "unit": "nghìn đồng, thang giá điều chỉnh hiện hành (theo kho nến DNSE)",
        "symbols": symbols,
    }
    if dry_run:
        for sym, d in symbols.items():
            p = d["profiles"].get("40") or {}
            print(f"{sym:6} giá {d['price']}  phiên {p.get('n')}/{p.get('n_real')} thật  POC ô {p.get('poc')}  "
                  f"mua {len(p.get('buy_zones', []))} vùng  bán {len(p.get('sell_zones', []))} vùng")
        return 0
    _dump(LATEST, latest)
    _dump(STATE, _state(now, src, collected, skipped, failed, warnings, wrote=True))
    log.info("Ghi %s: %d mã, phiên %s; mới %d, bỏ qua %d, lỗi %d", LATEST.name, len(symbols), trade_date,
             len(collected), len(skipped), len(failed))
    return 0 if not failed else 1


def _state(now, src, collected, skipped, failed, warnings, wrote: bool) -> dict:
    return {
        "ran_at": now.isoformat(timespec="seconds"),
        "wrote_latest": wrote,
        "watchlist_source": src,
        "collected": collected, "skipped": skipped, "failed": failed, "warnings": warnings,
        "vndirect_last_ok": vndirect.last_ok.isoformat(timespec="seconds") if vndirect.last_ok else "",
        "vndirect_last_error": vndirect.last_error,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="*", help="chỉ chạy các mã này (mặc định cả danh mục)")
    ap.add_argument("--force", action="store_true", help="gọi nguồn lại dù đã có phiên thật hôm nay, ghi đè")
    ap.add_argument("--dry-run", action="store_true", help="không ghi kho/latest, chỉ in tóm tắt")
    a = ap.parse_args()
    sys.exit(run(force=a.force, dry_run=a.dry_run, only=[s.upper() for s in a.symbols] or None))


if __name__ == "__main__":
    main()
