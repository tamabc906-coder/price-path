"""Cá mập ẩn — dò lệnh chia nhỏ nhịp đều (TWAP) và lệnh rổ trên tick của 39 mã, cùng lượt gom với job zone.

Nghiên cứu 03/10/2026 (bản mẫu c:\\Claude code\\algo-radar-lab): tổ chức cắt lệnh lớn thành lệnh con 100–300 tr
bắn đều theo nhịp — ngưỡng cá mập ≥ 500 tr/lệnh bỏ sót toàn bộ. Kiểm định bằng dữ liệu xáo (giữ thời điểm, xáo
phía + KL): chuỗi ≥ 8 lệnh cùng cỡ, CV khoảng cách < 0,3 → 92 chuỗi thật vs 2,8 xáo trên 39 mã × 4 phiên; rổ (≥ 5
mã cùng phía cùng giây) 162 thật vs 2 khi dịch giờ. Đếm chuỗi theo cỡ lệnh mà không xét nhịp thì ≈ mức xáo — đã bỏ.
CHƯA đo được sức dự báo giá (cần ≥ 60 phiên) → chỉ hiển thị, không push.

Kho: data/algo/<ngày>.json = {MÃ: symbol_day(...)}, ghi theo từng mã (lượt dự phòng gom bù mã thiếu vẫn ghép
được). Rổ tính lại từ kho mỗi lần dựng trang vì cần đủ cả danh mục cùng phiên.
Trang: docs/data/algo/index.json + docs/data/algo/<ngày>.json.
"""
from __future__ import annotations

import json
import logging
import random
import statistics as st
from collections import defaultdict
from datetime import datetime

from common.config import ROOT, SITE_DATA, TZ

log = logging.getLogger(__name__)

ALGO_DATA = ROOT / "data" / "algo"
ALGO_SITE = SITE_DATA / "algo"
KEEP_DATA = 60          # phiên giữ trong kho (đủ để đo khi tới ~60 phiên)
KEEP_SITE = 20          # phiên hiện trên app

# Ngưỡng cố định — chọn theo tỷ lệ báo nhầm trên dữ liệu xáo, KHÔNG chỉnh theo giá đi sau đó.
MIN_EVENTS = 100        # mã phải có ≥ 100 lệnh chủ động trong phiên
# 04/10/2026 nới theo soát lại (39 mã × 4 phiên, xáo 3 lần): luật cũ đòi nhịp hoàn hảo nên robot lỡ MỘT nhịp là mất
# cả chuỗi (TCB 30/09 mua 900 cp × 223 lệnh đúng 15 s, GMD 01/10 bán 2.000 × 104) — 92 chuỗi/154 tỷ, nhầm 2,5 % →
# luật nhịp cho phép lỡ 1–2 nhịp (cắt 600 s rồi 180 s, gộp luật cũ): 230 chuỗi/443 tỷ, nhầm 2,1 % (xáo 5 lần).
# 5–7 lệnh với CV (nhầm 14 %), lệnh < 500 cp (12 %), cỡ lệnh lệch 5 % (thêm ít) — không dùng.
CH_MIN_N = 6            # chuỗi ≥ 6 lệnh (luật nhịp) — luật CV cũ vẫn giữ ≥ 8 lệnh, cách ≤ 180 s
CH_GAP = 600            # hai lệnh liền nhau cách ≤ 600 giây
CH_STEP_TOL = 0.15      # khoảng cách ≈ k × nhịp (k = 1..3), sai ≤ 15 % nhịp
CH_STEP_OK = 0.85       # ≥ 85 % khoảng cách phải đạt
CV_MIN_N = 8            # luật cũ (A): ≥ 8 lệnh, cách ≤ 180 s, CV < 0,3
CV_GAP = 180
CH_MAX_CV = 0.3
CH_MIN_SIZE = 500       # cỡ lệnh ≥ 500 cp
BK_MIN_SYMS = 5         # rổ: ≥ 5 mã cùng phía cùng giây
BK_MIN_VND = 100_000_000  # mỗi lệnh trong rổ ≥ 100 tr đ
WHALE_VND = 500_000_000   # cá mập lệnh lớn — cùng ngưỡng zone
SKIP = {9 * 3600 + 15 * 60, 13 * 3600}   # 09:15:00 khớp mở cửa, 13:00:00 lệnh dồn nghỉ trưa
SHUFFLES = 5

# Giá tick là nghìn đồng → giá × KL × 1000 = VND.
_K = 1000


def _sec(t: str) -> int:
    h, m, s = (int(x) for x in t.split(":"))
    return h * 3600 + m * 60 + s


def events(ticks: list[dict]) -> tuple[list[list], float | None]:
    """Tick (cũ → mới) → lệnh chủ động [giây, "B"|"S", KL, giá] + giá ATC.

    Gộp mọi tick CÙNG GIÂY + CÙNG PHÍA thành một lệnh (một lệnh quét ăn nhiều mức giá — khác collect.orders gộp
    theo cả giá). VNDirect đặt tên theo bên bị động: PB = bán chủ động, PS = mua chủ động (zone/collect.py).
    """
    ev: list[list] = []
    atc = None
    for t in ticks:
        sd = t["side"]
        if sd == "ATC":
            atc = t["price"]
            continue
        if sd not in ("PB", "PS"):
            continue
        side = "S" if sd == "PB" else "B"
        s = _sec(t["time"])
        if ev and ev[-1][0] == s and ev[-1][1] == side:
            ev[-1][2] += t["vol"]
            ev[-1][3] = t["price"]
        else:
            ev.append([s, side, t["vol"], t["price"]])
    return ev, atc


def cv(times: list[int]) -> float:
    g = [b - a for a, b in zip(times, times[1:])]
    m = st.mean(g)
    return st.pstdev(g) / m if m > 0 else 9.0


def steady(times: list[int]) -> tuple[bool, int]:
    """(nhịp đều?, số nhịp lỡ). Nhịp m = trung vị khoảng cách; khoảng g đạt khi k = round(g/m) ∈ 1..3 và
    |g − k·m| ≤ CH_STEP_TOL·m — robot lỡ một lệnh con thì khoảng đó gấp đôi mà vẫn là cùng một nhịp."""
    g = [b - a for a, b in zip(times, times[1:])]
    m = st.median(g)
    if m <= 0:
        return False, 0
    good = miss = 0
    for x in g:
        k = round(x / m)
        if 1 <= k <= 3 and abs(x - k * m) <= CH_STEP_TOL * m:
            good += 1
            miss += k - 1
    return good >= CH_STEP_OK * len(g), miss


def _segments(idx: list[int], ev: list[list], gap: int) -> list[list[int]]:
    out, cur = [], [idx[0]]
    for i in idx[1:]:
        if ev[i][0] - ev[cur[-1]][0] <= gap:
            cur.append(i)
        else:
            out.append(cur)
            cur = [i]
    out.append(cur)
    return out


def chains(ev: list[list]) -> list[tuple[str, int, list[int]]]:
    """(phía, cỡ, chỉ số lệnh) cho mỗi chuỗi cùng phía + cùng KL chính xác (≥ CH_MIN_SIZE cp).

    Luật nhịp: đoạn cách ≤ CH_GAP, ≥ CH_MIN_N lệnh, steady(). Cộng thêm luật cũ (cách ≤ CV_GAP, ≥ CV_MIN_N,
    CV < CH_MAX_CV) cho phần chưa nằm trong chuỗi nào — để bản nới không làm mất chuỗi luật cũ đã bắt.
    """
    by: dict[tuple[str, int], list[int]] = defaultdict(list)
    for i, (_, side, v, _) in enumerate(ev):
        if v >= CH_MIN_SIZE:
            by[(side, v)].append(i)
    out = []
    for (side, v), idx in by.items():
        used: set[int] = set()
        # cắt 600 s trước (robot chậm), rồi 180 s cho phần còn lại: cùng cỡ lệnh có thể được bên khác đặt rải
        # trong phiên, đoạn 600 s dính vào đó thì lệch nhịp (TCB 25/09 mua 20.000 cp × 15 lệnh, 67 s/lệnh)
        for gap in (CH_GAP, CV_GAP):
            for seg in _segments(idx, ev, gap):
                if (len(seg) >= CH_MIN_N and not used.intersection(seg)
                        and steady([ev[j][0] for j in seg])[0]):
                    out.append((side, v, seg))
                    used.update(seg)
        for seg in _segments(idx, ev, CV_GAP):
            if len(seg) >= CV_MIN_N and not used.intersection(seg) and cv([ev[j][0] for j in seg]) < CH_MAX_CV:
                out.append((side, v, seg))
    return out


def shuffled(ev: list[list], seed: int) -> list[list]:
    """Mức giả: giữ thời điểm + giá, xáo (phía, KL) giữa các lệnh trong ngày."""
    sz = [(e[1], e[2]) for e in ev]
    random.Random(seed).shuffle(sz)
    return [[e[0], a, b, e[3]] for e, (a, b) in zip(ev, sz)]


def candles5(ev: list[list]) -> list[list]:
    """Nến 5' từ lệnh chủ động: [giây đầu nến, o, h, l, c, KL mua, KL bán]."""
    out: dict[int, list] = {}
    for s, side, v, p in ev:
        k = s // 300 * 300
        c = out.get(k)
        if c is None:
            c = out[k] = [k, p, p, p, p, 0, 0]
        c[2] = max(c[2], p)
        c[3] = min(c[3], p)
        c[4] = p
        c[5 if side == "B" else 6] += v
    return [out[k] for k in sorted(out)]


def symbol_day(ticks: list[dict]) -> dict | None:
    """Bản ghi một mã một phiên; None nếu quá ít lệnh để dò."""
    ev, atc = events(ticks)
    if len(ev) < MIN_EVENTS:
        return None
    cs = chains(ev)
    in_ch = {j for _, _, idx in cs for j in idx}
    tot_vol = sum(e[2] for e in ev)
    tot_val = sum(e[2] * e[3] * _K for e in ev)
    whale = [0.0, 0.0]
    big = []
    for i, (s, side, v, p) in enumerate(ev):
        val = v * p * _K
        if val >= WHALE_VND:
            whale[side == "S"] += val
        if val >= BK_MIN_VND:
            # w = 1: lệnh đã được tính vào lớp cá mập (lệnh lớn hoặc lệnh con chuỗi) → trừ khi nó rơi vào rổ
            big.append([s, side, round(val / 1e6), int(val >= WHALE_VND or i in in_ch)])
    out_ch = []
    for side, v, idx in cs:
        ts = [ev[j][0] for j in idx]
        ps = [ev[j][3] for j in idx]
        out_ch.append({"side": side, "size": v, "t": ts, "p": ps, "cv": round(cv(ts), 3), "miss": steady(ts)[1]})
    out_ch.sort(key=lambda c: c["t"][0])
    fake = sum(len(chains(shuffled(ev, k))) for k in range(SHUFFLES)) / SHUFFLES
    return {
        "n": len(ev), "open": ev[0][3], "close": atc if atc is not None else ev[-1][3],
        "vwap": round(tot_val / _K / tot_vol, 3), "val": round(tot_val / 1e9, 2),
        "whale": [round(whale[0] / 1e9, 2), round(whale[1] / 1e9, 2)],
        "chains": out_ch, "fake": round(fake, 2), "big": big, "c5": candles5(ev),
    }


# ---------------------------------------------------------------- kho


def _load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def _dump(path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def put(day: str, symbol: str, rec: dict | None) -> None:
    """Ghép bản ghi một mã vào data/algo/<ngày>.json (None = mã quá ít lệnh, vẫn ghi để biết đã xét)."""
    path = ALGO_DATA / f"{day}.json"
    doc = _load(path, {})
    doc[symbol] = rec
    _dump(path, dict(sorted(doc.items())))


def prune() -> None:
    for p in sorted(ALGO_DATA.glob("*.json"))[:-KEEP_DATA]:
        p.unlink()


# ---------------------------------------------------------------- dựng trang


def basket_keys(day_doc: dict, shift: bool = False) -> dict[tuple[int, str], list]:
    """(giây, phía) → [(mã, tr đ)] cho các giây có ≥ BK_MIN_SYMS mã. shift=True: dịch giờ mỗi mã ±30' (mức giả)."""
    g: dict[tuple[int, str], list] = defaultdict(list)
    rnd = random.Random(7)
    for sym in sorted(day_doc):
        rec = day_doc[sym]
        if not rec:
            continue
        sh = rnd.randint(-1800, 1800) if shift else 0
        for s, side, tr, _ in rec["big"]:
            if s not in SKIP:
                g[(s + sh, side)].append((sym, tr))
    return {k: L for k, L in g.items() if len({x[0] for x in L}) >= BK_MIN_SYMS}


def day_view(day: str, doc: dict, prev_doc: dict | None, closes: dict[str, dict[str, float]]) -> dict:
    """Dữ liệu hiển thị một phiên: thẻ từng mã + rổ + kiểm định thật/xáo."""
    bk = basket_keys(doc)
    in_bk = {(sym, s, side) for (s, side), L in bk.items() for sym, _ in L}
    prev = set()
    for sym, rec in (prev_doc or {}).items():
        for c in (rec or {}).get("chains", []):
            prev.add((sym, c["side"], c["size"]))
    stocks = []
    ch_real = ch_fake = 0.0
    for sym, rec in doc.items():
        if not rec:
            continue
        ch_real += len(rec["chains"])
        ch_fake += rec["fake"]
        sg = {"B": 1, "S": -1}
        algo = 0.0
        waves: dict[tuple[str, int], int] = defaultdict(int)
        for c in rec["chains"]:
            waves[(c["side"], c["size"])] += 1
        chs = []
        for c in rec["chains"]:
            val = sum(c["size"] * p * _K for p in c["p"])
            algo += sg[c["side"]] * val
            gaps = [b - a for a, b in zip(c["t"], c["t"][1:])]
            chs.append({**c, "n": len(c["t"]), "step": int(st.median(gaps)), "val": round(val / 1e9, 2),
                        "pct": round(100 * val / 1e9 / rec["val"], 1) if rec["val"] else 0,
                        "avg": round(sum(c["p"]) / len(c["p"]), 3),
                        "waves": waves[(c["side"], c["size"])],
                        "carry": (sym, c["side"], c["size"]) in prev})
        bk_net = 0.0
        bk_cm = 0.0
        bkt = []
        for s, side, tr, w in rec["big"]:
            if (sym, s, side) in in_bk:
                bk_net += sg[side] * tr
                bkt.append([s, side, tr])
                if w:
                    bk_cm += sg[side] * tr
        # chuỗi con < 500 tr không thuộc whale: cá mập tổng hợp = lệnh lớn + lệnh con chuỗi, bỏ phần trùng
        whale_net = rec["whale"][0] - rec["whale"][1]
        overlap = 0.0
        for c in rec["chains"]:
            for p in c["p"]:
                v = c["size"] * p * _K
                if v >= WHALE_VND:
                    overlap += sg[c["side"]] * v
        comb = whale_net + (algo - overlap) / 1e9 - bk_cm / 1e3
        cl = closes.get(sym, {})
        days = sorted(d for d in cl if d <= day)
        chg = None
        if len(days) >= 2 and days[-1] == day and cl[days[-2]]:
            chg = round(100 * (cl[day] / cl[days[-2]] - 1), 2)
        stocks.append({
            "sym": sym, "close": rec["close"], "chg": chg, "vwap": rec["vwap"], "val": rec["val"],
            "algo": round(algo / 1e9, 2), "whale": round(whale_net, 2), "bk": round(bk_net / 1e3, 2),
            "comb": round(comb, 2), "chains": chs, "bkt": bkt, "c5": rec["c5"],
        })
    stocks.sort(key=lambda x: (0 if x["chains"] else 1, -abs(x["algo"])))
    baskets = [{"t": s, "side": side, "n": len({x[0] for x in L}), "val": round(sum(x[1] for x in L) / 1e3, 2),
                "m": sorted({x[0] for x in L})} for (s, side), L in sorted(bk.items())]
    return {
        "day": day, "nsym": sum(1 for r in doc.values() if r),
        "test": {"ch_real": int(ch_real), "ch_fake": round(ch_fake, 1),
                 "bk_real": len(bk), "bk_fake": len(basket_keys(doc, shift=True))},
        "stocks": stocks, "baskets": baskets,
    }


def build_site(closes: dict[str, dict[str, float]] | None = None) -> int:
    """Dựng docs/data/algo/ từ kho (KEEP_SITE phiên gần nhất). Trả số phiên đã dựng."""
    closes = closes or {}
    files = sorted(ALGO_DATA.glob("*.json"))
    if not files:
        return 0
    prune()
    files = sorted(ALGO_DATA.glob("*.json"))[-(KEEP_SITE + 1):]
    docs = [(p.stem, _load(p, {})) for p in files]
    index = []
    for i, (day, doc) in enumerate(docs):
        if i == 0 and len(docs) > KEEP_SITE:
            continue        # phiên dư chỉ để gắn nhãn "tiếp từ phiên trước" cho phiên kế
        view = day_view(day, doc, docs[i - 1][1] if i else None, closes)
        _dump(ALGO_SITE / f"{day}.json", view)
        index.append({"day": day, "nsym": view["nsym"], "test": view["test"],
                      "n_chains": view["test"]["ch_real"],
                      "algo": round(sum(s["algo"] for s in view["stocks"]), 2)})
    keep = {d["day"] for d in index}
    for p in ALGO_SITE.glob("2*.json"):
        if p.stem not in keep:
            p.unlink()
    _dump(ALGO_SITE / "index.json", {
        "updated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "rule": {"n": CH_MIN_N, "cv": CH_MAX_CV, "gap": CH_GAP, "size": CH_MIN_SIZE,
                 "tol": CH_STEP_TOL, "ok": CH_STEP_OK, "cv_n": CV_MIN_N, "cv_gap": CV_GAP,
                 "bk_syms": BK_MIN_SYMS, "bk_tr": BK_MIN_VND // 1_000_000, "whale_tr": WHALE_VND // 1_000_000},
        "days": index,
    })
    return len(index)
