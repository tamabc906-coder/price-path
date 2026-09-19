"""Chạy lại N phiên gần nhất bằng đúng pipeline của job để (1) mồi hệ số giãn conformal thay vì bắt đầu
ở 1,0 mù, (2) có sẵn sổ chấm điểm (docs/data/daily/*.json + state.scores) ngay ngày đầu chạy thật.

    venv\\Scripts\\python -m scripts.backfill --sessions 80 --n 600

Mỗi phiên d: đặc trưng chỉ tới d; pool chỉ từ hàng có t+20 ≤ d (không nhìn tương lai); ghi daily/<d>.json;
rồi chấm các nón đến hạn tại d và cập nhật s — y như job thật chạy tuần tự. KHÔNG push, không ghi latest.json.
Xoá daily/ và conformal_state.json cũ trước khi chạy (hỏi trước nếu đã có dữ liệu thật).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date

import pandas as pd

from common import store as store_mod
from common.config import HISTORY, INDEX_SYMBOL, SITE_DATA
from job import forecast, settings, watchlist
from model import conformal, regime
from model.features import build_all

for s in (sys.stdout, sys.stderr):
    if hasattr(s, "reconfigure"):
        s.reconfigure(encoding="utf-8", errors="replace")

DAILY = SITE_DATA / "daily"
STATE = SITE_DATA / "state.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, default=80)
    ap.add_argument("--n", type=int, default=600, help="số đường mô phỏng mỗi mã (job thật 2000)")
    ap.add_argument("--yes", action="store_true", help="ghi đè daily/ và conformal_state.json không hỏi")
    a = ap.parse_args()

    existing = sorted(DAILY.glob("*.json")) if DAILY.exists() else []
    if existing and not a.yes:
        print(f"daily/ đã có {len(existing)} file ({existing[0].name} → {existing[-1].name}). Thêm --yes để ghi đè.", file=sys.stderr)
        return 2
    for p in existing:
        p.unlink()

    hist = store_mod.load(HISTORY)
    items, src = watchlist.load()
    cfg = settings.load()
    syms = sorted(it["symbol"] for it in items)
    print(f"đặc trưng {len(syms)} mã…", file=sys.stderr)
    f_all = build_all(hist, syms, INDEX_SYMBOL, store_mod.bars)
    keys_all = regime.keys_for(f_all)
    cal = forecast.calendar(hist)
    days = cal[-a.sessions:]
    conf_state = conformal.new_state(forecast.HS)
    scored: set[str] = set()
    scores: list[dict] = []
    DAILY.mkdir(parents=True, exist_ok=True)
    for k, d in enumerate(days, 1):
        di = cal.index(d)
        d_ts = pd.Timestamp(d)
        f = f_all[f_all["d"] <= d_ts]
        keys = keys_all.loc[f.index]
        pool_cut = pd.Timestamp(cal[di - 20]) if di >= 20 else None
        sub = f[f["d"] <= pool_cut] if pool_cut is not None else f.iloc[0:0]
        pools = regime.build_pools(sub, keys.loc[sub.index])
        td = date.fromisoformat(d)
        new_scores = forecast.score_matured(hist, cal, td, DAILY, conf_state, scored)
        scores += new_scores
        fc, stale, info = forecast.forecast_from(f, keys, pools, items, td, cfg, conf_state, n_sim=a.n)
        alerts = [it["symbol"] for it in fc if it.get("ok") and it["alert"]]
        (DAILY / f"{d}.json").write_text(json.dumps({
            "trade_date": d, "generated_at": f"backfill", "late": False,
            "forecasts": {it["symbol"]: {"price": it["price"], "q_log": it["q_log"], "p10": it["p10"],
                                         "alert": it["alert"], "level": it["level"], "n": it["n"]} for it in fc if it.get("ok")},
            "alerts": alerts, "stale": stale}, ensure_ascii=False, indent=1), encoding="utf-8")
        s80 = conformal.scale(conf_state, 10, 80)
        print(f"  {k:>3}/{len(days)} {d} · {sum(1 for x in fc if x.get('ok'))} dự báo · {len(alerts)} qua ngưỡng · "
              f"chấm {len(new_scores)} · s(10,80)={s80:.3f}", file=sys.stderr)
    forecast.save_conf_state(conf_state)
    st = {}
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        pass
    st.update({"scores": scores[-400:], "scored": sorted(scored)[-600:], "backfill": {"sessions": len(days), "n": a.n,
               "from": days[0], "to": days[-1]}})
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    v = forecast.verdict(conf_state)
    print(f"Xong. {v['text']} · cov60={v['cov']} · s={v['s']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
