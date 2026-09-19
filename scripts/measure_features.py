"""Phép đo: đặc trưng giá + khối lượng 20 phiên gần nhất có nói gì về 20 phiên tới không?

    venv\\Scripts\\python -m scripts.measure_features            # in bảng ra màn hình
    venv\\Scripts\\python -m scripts.measure_features --md > reports/measure-20-phien-<ngày>.md

Không đụng app. Với mỗi phiên t của mỗi mã (39 mã, 2016 → 2026) tính các đặc trưng chỉ dùng nến ≤ t, rồi
xem lợi suất log 20 phiên SAU (fr20 = ln(c[t+20]/c[t])) phân bố thế nào theo từng nhóm đặc trưng:
  * mean fr20 (%)     — nghiêng về bên nào
  * thắng (%)         — tỷ lệ fr20 > 0
  * std fr20 (%)      — nón rộng bao nhiêu (đây là thứ 20 phiên quá khứ dự báo tốt nhất)
  * năm > mua-đại     — số năm mà mean của nhóm cao hơn mean toàn bộ ("mua đại") trong cùng năm / số năm
Mốc so sánh là "mua đại": mọi phiên, mọi mã. Cửa sổ 20 phiên chồng nhau nên KHÔNG in t-stat (sẽ ảo);
tính nhất quán theo năm là thước đo chính (bài học ADX/MA, Ba bước giảm).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

import numpy as np
import pandas as pd

from common import store
from common.config import HISTORY, INDEX_SYMBOL
from job import trend

for s in (sys.stdout, sys.stderr):
    if hasattr(s, "reconfigure"):
        s.reconfigure(encoding="utf-8", errors="replace")

H = 20
FROM_YEAR = 2016


def frame(bars: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(bars)[["d", "o", "h", "l", "c", "v"]].copy()
    df["d"] = pd.to_datetime(df["d"])
    return df.reset_index(drop=True)


def features(df: pd.DataFrame, bars: list[dict]) -> pd.DataFrame:
    c, o, h, l, v = df["c"], df["o"], df["h"], df["l"], df["v"].astype(float)
    r1 = np.log(c / c.shift(1))
    f = pd.DataFrame({"d": df["d"], "c": c})
    f["r20"] = np.log(c / c.shift(20))
    f["vol20"] = r1.rolling(20).std()
    # Garman-Klass 20 phiên từ O/H/L/C
    gk = 0.5 * np.log(h / l) ** 2 - (2 * np.log(2) - 1) * np.log(c / o) ** 2
    f["gk20"] = np.sqrt(gk.rolling(20).mean().clip(lower=0))
    # phân vị của biến động hôm nay trong 250 phiên trước (0..1)
    for col in ("vol20", "gk20"):
        f[col + "_rank"] = f[col].rolling(250).apply(lambda x: float((x[-1] > x[:-1]).mean()), raw=True)
    vma20 = v.rolling(20).mean()
    f["vol_ratio"] = v / vma20
    f["vol_spike3"] = (f["vol_ratio"].rolling(3).max() >= 2.0)
    # KL đi cùng chiều giá: tỷ trọng KL của các phiên tăng trong 20 phiên
    up = (c > c.shift(1)).astype(float)
    f["upvol_share"] = (v * up).rolling(20).sum() / v.rolling(20).sum()
    f["gap"] = o / c.shift(1) - 1
    # trần + KL bùng nổ + phá đỉnh 20 phiên (cùng điều kiện job/patterns.py::_limit_up_climax)
    body = (c - o).abs()
    avg_body = body.rolling(10).mean().shift(1)
    rng = (h - l).replace(0, np.nan)
    chg = c / c.shift(1) - 1
    climax = ((chg >= 0.065) & (c > o) & (body >= 2 * avg_body) & ((c - l) / rng >= 0.8)
              & (v >= 2 * vma20.shift(1)) & (c > c.shift(1).rolling(20).max()))
    f["climax3"] = climax.rolling(3).max().astype(bool)
    st = trend.supertrend(bars)
    em = trend.ema(bars)
    f["st_up"] = [x["up"] if x else np.nan for x in st]
    f["ema_above"] = [(b["c"] > e) if e is not None else np.nan for b, e in zip(bars, em)]
    # nhãn
    f["fr20"] = np.log(c.shift(-H) / c)
    f["fr10"] = np.log(c.shift(-10) / c)
    return f


def index_regime(bars: list[dict]) -> pd.DataFrame:
    df = frame(bars)
    st = trend.supertrend(bars)
    em50 = trend.ema(bars, 50)
    up = [(x["up"] and b["c"] > e) if (x and e is not None) else np.nan for x, e, b in zip(st, em50, bars)]
    return pd.DataFrame({"d": df["d"], "idx_up": up})


def bucketize(f: pd.DataFrame) -> pd.DataFrame:
    b = pd.DataFrame(index=f.index)
    b["Biến động 20p (std, phân vị 250p)"] = pd.cut(f["vol20_rank"], [-0.01, 0.33, 0.67, 1.01], labels=["thấp", "vừa", "cao"])
    b["Biến động 20p (Garman-Klass, phân vị)"] = pd.cut(f["gk20_rank"], [-0.01, 0.33, 0.67, 1.01], labels=["thấp", "vừa", "cao"])
    b["KL hôm nay / TB20"] = pd.cut(f["vol_ratio"], [0, 0.7, 1.5, 2.0, 99], labels=["cạn <0,7×", "thường", "cao 1,5–2×", "bất thường ≥2×"])
    b["Có phiên KL ≥2× trong 3p"] = f["vol_spike3"].map({True: "có", False: "không"})
    b["Tỷ trọng KL phiên tăng (20p)"] = pd.cut(f["upvol_share"], [-0.01, 0.4, 0.6, 1.01], labels=["<40 % (KL dồn phiên giảm)", "40–60 %", ">60 % (KL dồn phiên tăng)"])
    b["Lợi suất 20p vừa qua"] = pd.cut(f["r20"], [-9, -0.05, 0.05, 9], labels=["< −5 %", "−5…+5 %", "> +5 %"])
    b["Trần+KL+phá đỉnh trong 3p"] = f["climax3"].map({True: "có", False: "không"})
    b["Gap mở cửa hôm nay"] = pd.cut(f["gap"], [-1, -0.01, 0.01, 1], labels=["< −1 %", "−1…+1 %", "> +1 %"])
    st = f["st_up"].map({True: "ST xanh", False: "ST đỏ"})
    ema = f["ema_above"].map({True: "trên EMA10", False: "dưới EMA10"})
    b["Supertrend × EMA10"] = (st + " · " + ema)
    b["VN-Index (ST xanh & trên EMA50)"] = f["idx_up"].map({True: "tăng", False: "giảm"})
    # tổ hợp: trần+KL trong 3p × KL dồn phiên tăng
    b["Trần+KL 3p × KL dồn phiên tăng"] = np.where(f["climax3"] & (f["upvol_share"] > 0.6), "cả hai",
                                                   np.where(f["climax3"], "chỉ trần+KL", "không"))
    return b


def table(f: pd.DataFrame, b: pd.DataFrame, col: str, md: bool) -> str:
    years = sorted(f["year"].unique())
    base_year = f.groupby("year")["fr20"].mean()
    base_all = f["fr20"].mean()
    rows = []
    for lab, g in f.groupby(b[col], observed=True):
        if len(g) < 200:
            continue
        by = g.groupby("year")["fr20"].mean()
        beat = sum(1 for y in years if y in by.index and by[y] > base_year[y])
        rows.append((str(lab), len(g), g["fr20"].mean() * 100, (g["fr20"] > 0).mean() * 100,
                     g["fr20"].std() * 100, f"{beat}/{len(years)}"))
    rows.append(("— mua đại (mọi phiên) —", len(f), base_all * 100, (f["fr20"] > 0).mean() * 100, f["fr20"].std() * 100, "—"))
    if md:
        out = [f"### {col}", "", "| Nhóm | n | mean fr20 | thắng | std fr20 | năm > mua-đại |", "|---|---:|---:|---:|---:|:---:|"]
        for r in rows:
            out.append(f"| {r[0]} | {r[1]:,} | {r[2]:+.2f} % | {r[3]:.1f} % | {r[4]:.1f} % | {r[5]} |")
        return "\n".join(out) + "\n"
    out = [f"\n{col}", f"{'Nhóm':<34}{'n':>8}{'mean':>9}{'thắng':>8}{'std':>8}{'năm>MĐ':>9}"]
    for r in rows:
        out.append(f"{r[0]:<34}{r[1]:>8,}{r[2]:>+8.2f}%{r[3]:>7.1f}%{r[4]:>7.1f}%{r[5]:>9}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", action="store_true")
    a = ap.parse_args()
    st = store.load(HISTORY)
    idx = index_regime(store.bars(st, INDEX_SYMBOL))
    parts = []
    for sym in sorted(st["bars"]):
        if sym == INDEX_SYMBOL:
            continue
        bars = store.bars(st, sym)
        if len(bars) < 300:
            continue
        f = features(frame(bars), bars)
        f["symbol"] = sym
        parts.append(f)
    f = pd.concat(parts, ignore_index=True).merge(idx, on="d", how="left")
    f["year"] = f["d"].dt.year
    f = f[(f["year"] >= FROM_YEAR) & f["fr20"].notna() & f["vol20_rank"].notna()].copy()
    b = bucketize(f)
    nsym = f["symbol"].nunique()
    head = (f"Phép đo 20 phiên → 20 phiên · {nsym} mã · {f['d'].min().date()} → {f['d'].max().date()} · "
            f"{len(f):,} phiên-mã · lợi suất log 20 phiên sau, chưa phí. Cửa sổ chồng nhau: đọc cột 'năm > mua-đại', đừng tin std sai số.")
    out = [("# " + head + "\n") if a.md else head]
    for col in b.columns:
        out.append(table(f, b, col, a.md))
    # riêng phần "nón rộng bao nhiêu": std fr20 theo tam phân vị biến động, từng năm
    lab = "Biến động 20p (std, phân vị 250p)"
    piv = f.assign(bk=b[lab]).groupby(["year", "bk"], observed=True)["fr20"].std().unstack() * 100
    if a.md:
        out.append("### Nón rộng bao nhiêu — std fr20 (%) theo nhóm biến động, từng năm\n")
        out.append("| Năm | " + " | ".join(piv.columns.astype(str)) + " | cao/thấp |")
        out.append("|---|" + "---:|" * (len(piv.columns) + 1))
        for y, r in piv.iterrows():
            out.append(f"| {y} | " + " | ".join(f"{x:.1f}" for x in r.values) + f" | {r.iloc[-1]/r.iloc[0]:.2f}× |")
        out.append("")
    else:
        out.append("\nstd fr20 (%) theo nhóm biến động, từng năm (cột cuối = cao/thấp):")
        out.append(piv.assign(ratio=piv.iloc[:, -1] / piv.iloc[:, 0]).round(2).to_string())
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
