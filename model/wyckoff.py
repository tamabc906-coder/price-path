"""CHÉP NGUYÊN từ wyckoff-radar/job/wyckoff.py (23/09/2026) — price-path chỉ dùng sự kiện "sc" qua model/events.py.
Sửa ở wyckoff-radar trước rồi chép lại; đừng sửa riêng bản này.

Lõi Wyckoff: máy trạng thái vùng đi ngang (trading range — TR) + sự kiện trên nến ngày. Thuần hàm, không I/O.

Nguồn ngưỡng (kế hoạch Phần 2, báo cáo Researcher 21/09/2026): Villahermosa/tradingwyckoff.com (3 loại Spring,
Test, SOS "KL +50–100 %"), EricCatalan/Trading-POC (độ dốc TR, stop = đáy − 0,5×ATR), StockCharts (định tính),
wyckoffanalytics.com (spring không đóng ở đáy phiên). Wyckoff gốc KHÔNG công bố số — mọi ngưỡng ở CFG là điểm
khởi đầu để scripts/measure.py đo; chỉ sự kiện đạt ★ mới push.

Nhân quả: `analyze(bars)` quét tuần tự, sự kiện gắn tại nến i chỉ dùng nến ≤ i (AR chốt sau SC 8 phiên nên
`at` = nến phát hiện, `i` = nến sự kiện). Vì thế tín hiệu "hôm nay" = sự kiện có at == nến cuối, và replay
lịch sử cho đúng thứ job sẽ thấy vào ngày đó.

Ký hiệu: av = KL trung bình 20 nến TRƯỚC i; atr = ATR Wilder 14; spread = h−l; close_pos = (c−l)/(h−l).
Cờ sàn/trần (±6,5 % so đóng cửa hôm trước) → bỏ điều kiện spread vì biên độ HOSE nén nến nhân tạo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

MIN_BARS = 40

CFG = {
    "vol_n": 20, "atr_n": 14,
    "limit_pct": 0.065,                 # cờ sàn/trần
    # SC / BC
    # sc_close_pos = 0: KHÔNG đòi đóng cửa hồi khỏi đáy — ở VN ngày cao trào thường đóng sát sàn, hôm sau mới bật
    # (đo 21/09/2026: điều kiện 0,3 loại 259/295 ứng viên; demand-candle-lab +2,36 %/10p cũng không cần).
    "climax_drop": 0.10, "climax_win": 15, "climax_vol": 2.0, "climax_spread": 1.5, "sc_close_pos": 0.0,
    # AR
    "ar_min": 3, "ar_max": 8, "ar_pct": 0.05,
    # TR
    "tr_tol": 0.03, "tr_min": 20, "tr_max": 120, "tr_exit_bars": 2,
    # vùng gốc "range" (sơ đồ #2): 20 phiên đi ngang SAU một đợt giảm ≥ 10 % (bối cảnh tích lũy), tuổi tính từ lúc
    # phát hiện nên phải đi ngang thêm ≥ tr_min phiên nữa mới xét tín hiệu
    "range_win": 20, "range_height_max": 0.35, "range_height_min": 0.06, "range_slope": 0.004, "range_touch": 0.15,
    "range_prior_drop": 0.10, "range_prior_win": 40,
    # ST
    "st_vol": 0.7, "st_near": 0.03,
    # Spring (Villahermosa): #3 phá <1 % KL ≤ 0,7×; #2 1–3 %; #1 3–6 %
    "spring3_break": 0.01, "spring2_break": 0.03, "spring1_break": 0.06, "spring3_vol": 0.7, "spring_close_pos": 0.5,
    "spring_recover_bars": 3,
    # Test
    "test_min": 2, "test_max": 10, "test_vol": 0.5, "test_spread": 0.6, "test_close_pos": 0.5,
    # SOS / SOW
    "sos_body": 1.5, "sos_vol": 1.5, "sos_close_pos": 0.7,
    # LPS / BU
    # LPS: đáy nhịp lùi không sâu quá 35 % biên độ vùng tính từ creek (Wyckoff: LPS có thể nằm trong vùng)
    "lps_min": 2, "lps_max": 20, "lps_depth": 0.35, "lps_vol": 0.8, "bu_band": 0.02,
    # markup/markdown hết hiệu lực sau ngần này phiên, hoặc khi giá đi ngược hẳn qua biên vùng cũ: mốc "đáy LPS"
    # của một vùng đã kết thúc 8 tháng trước không còn là mốc Wyckoff hợp lệ (HCM 22/09/2026 mang nhãn "đang giảm"
    # suốt 8 tháng dù giá tăng 27 %).
    "markup_max": 60,
    # UT
    "ut_vol": 1.5, "ut_close_pos": 0.3, "utad_break": 0.05,
    # nhãn
    "er_vol": 2.0, "er_ratio": 0.5, "nd_spread": 0.7,
    "stop_atr": 0.5,
}

# id → mô tả. direction: buy | exit | watch | label. priority nhỏ = tin cậy hơn (thứ tự Bruce Fraser/Villahermosa).
EVENTS = {
    "sc":      {"name": "Bán tháo cao trào (SC)", "direction": "buy", "priority": 6,
                "hint": "KL rất lớn sau đợt giảm dài, đóng cửa hồi khỏi đáy — cầu lớn hấp thụ cung hoảng loạn.",
                "advice": "Chỉ dò 1/3 vị thế; chờ AR/ST xác lập vùng rồi mới thêm.",
                "caution": "Chưa có vùng tích lũy. Sàn liên tiếp nhiều phiên thì SC có thể chưa phải đáy."},
    "ar":      {"name": "Hồi phục tự động (AR)", "direction": "watch", "priority": 90,
                "hint": "Bật mạnh vì cung tạm cạn — đỉnh AR là biên trên (creek) của vùng.", "advice": "", "caution": ""},
    "st":      {"name": "Kiểm tra thứ cấp (ST)", "direction": "watch", "priority": 80,
                "hint": "Quay lại vùng SC với KL và spread nhỏ hơn — cung đã yếu.", "advice": "Chưa mua; vùng bắt đầu xây nguyên nhân.", "caution": ""},
    "spring3": {"name": "Spring #3 (KL thấp)", "direction": "buy", "priority": 1,
                "hint": "Phá đáy vùng < 1 % rồi đóng lại bên trong, KL ≤ 0,7× TB — cung đã cạn.",
                "advice": "Mua mở phiên mai, tối đa 1/3 vị thế; thêm khi có LPS.", "caution": "Stop dưới đáy spring − 0,5×ATR."},
    # Đo 2016→2026 (reports/measure-2026-09-22.md): −2,66 %/10p, t −4,4, thua mua-đại 8/10 năm — ở VN cú thủng đáy vùng
    # 1–3 % rồi đóng lại là RÒ RỈ, không phải bẫy mua như sách. Người dùng chốt 22/09/2026: dùng làm cảnh báo THOÁT.
    # Phát hiện sau khi đo (không phải giả thuyết đặt trước) → đo lại sau 3 tháng bằng tab Lịch sử.
    "spring2": {"name": "Spring #2 — rò rỉ đáy vùng", "direction": "exit", "priority": 14,
                "hint": "Thủng đáy vùng 1–3 % rồi đóng lại bên trong với KL vừa — sách gọi là spring, số đo VN nói 10 phiên sau thường thấp hơn.",
                "advice": "Đang giữ → thoát hoặc siết stop sát đáy vừa thủng; chưa giữ → không mua. Chỉ thành spring thật nếu 2–10 phiên sau có Test KL < ½.",
                "caution": "Phát hiện sau khi đo — đo lại sau 3 tháng."},
    "spring1": {"name": "Spring #1 / Shakeout", "direction": "watch", "priority": 51,
                "hint": "Phá đáy 3–6 % với KL lớn — rũ bỏ, cung còn; bắt buộc có Test.", "advice": "Chờ Test.", "caution": "Không mua ngay."},
    "test":    {"name": "Test sau Spring", "direction": "buy", "priority": 2,
                "hint": "Lùi về gần đáy spring với KL < ½ KL spring, spread hẹp, đóng cửa nửa trên, giữ trên đáy spring.",
                "advice": "Mua mở phiên mai; stop dưới đáy spring − 0,5×ATR.", "caution": ""},
    "sos":     {"name": "Dấu hiệu sức mạnh (SOS)", "direction": "buy", "priority": 4,
                "hint": "Nến tăng thân ≥ 1,5×ATR, KL ≥ 1,5× TB, đóng cửa cao, vượt biên trên vùng ≥ 20 phiên.",
                "advice": "Mua theo đà tối đa 1/3; điểm vào an toàn hơn là LPS/BU sau đó.", "caution": "Đừng đuổi nếu đã xa creek > 5 %."},
    "lps":     {"name": "Điểm hỗ trợ cuối (LPS)", "direction": "buy", "priority": 3,
                "hint": "Nhịp lùi sau SOS giữ trên creek với KL thấp, rồi nến tăng đóng trên đỉnh nhịp lùi.",
                "advice": "Điểm vào chính theo Wyckoff; stop dưới đáy LPS − 0,5×ATR.", "caution": ""},
    "bu":      {"name": "Lùi về creek (BU)", "direction": "buy", "priority": 5,
                "hint": "Giá về sát biên trên cũ (±2 %) với KL giảm dần 3 phiên — kháng cự thành hỗ trợ.",
                "advice": "Mua dò; xác nhận khi có LPS.", "caution": "Sớm hơn LPS nên rủi ro hơn."},
    "ut":      {"name": "Upthrust (UT)", "direction": "watch", "priority": 60,
                "hint": "Phá biên trên rồi đóng lại bên trong với KL cao — bẫy mua.", "advice": "Không mua đuổi.", "caution": ""},
    "bc":      {"name": "Mua cao trào (BC)", "direction": "exit", "priority": 12,
                "hint": "KL rất lớn sau đợt tăng dài, đóng cửa xa đỉnh — cung lớn xuất hiện.", "advice": "Giảm tỷ trọng.", "caution": ""},
    "utad":    {"name": "Upthrust sau phân phối (UTAD)", "direction": "exit", "priority": 11,
                "hint": "Phá đỉnh vùng phân phối rồi đóng lại bên trong — kiểm tra cuối trước khi giảm.", "advice": "Thoát / không mua thêm.", "caution": ""},
    "sow":     {"name": "Dấu hiệu suy yếu (SOW)", "direction": "exit", "priority": 10,
                "hint": "Nến giảm rộng, KL lớn, phá đáy vùng phân phối hoặc đáy LPS đang tăng.", "advice": "Thoát toàn bộ.",
                "caution": "5/5 năm đúng chiều nhưng chưa đủ 6 năm mẫu — đo lại sau 3 tháng."},
    "lpsy":    {"name": "Điểm cung cuối (LPSY)", "direction": "exit", "priority": 13,
                "hint": "Hồi phục yếu sau SOW, KL thấp, không vượt lại đáy vùng cũ.", "advice": "Không mua lại.", "caution": ""},
    "er_absorb": {"name": "Nỗ lực không kết quả", "direction": "label", "priority": 95,
                  "hint": "KL ≥ 2× TB nhưng thân nến nhỏ so ATR — có bên hấp thụ.", "advice": "", "caution": ""},
    "no_demand": {"name": "Không có cầu", "direction": "label", "priority": 96,
                  "hint": "Nến tăng KL thấp hơn 2 phiên trước, spread hẹp — đà tăng không có lực.", "advice": "", "caution": ""},
}


# ---------- tiện ích nến ----------

def spread(b: dict) -> float:
    return b["h"] - b["l"]


def body(b: dict) -> float:
    return abs(b["c"] - b["o"])


def close_pos(b: dict) -> float:
    r = spread(b)
    return (b["c"] - b["l"]) / r if r > 0 else 0.5


def is_bull(b: dict) -> bool:
    return b["c"] > b["o"]


def is_bear(b: dict) -> bool:
    return b["c"] < b["o"]


def avg_vol(bars: list[dict], i: int, n: int = 20) -> float:
    w = bars[max(0, i - n):i]
    return sum(x["v"] for x in w) / len(w) if w else 0.0


def atr_wilder(bars: list[dict], n: int = 14) -> list[Optional[float]]:
    """True range rồi RMA Wilder; None khi chưa đủ n nến."""
    out: list[Optional[float]] = [None] * len(bars)
    trs: list[float] = []
    prev: Optional[float] = None
    for i, b in enumerate(bars):
        tr = spread(b) if prev is None else max(spread(b), abs(b["h"] - prev), abs(b["l"] - prev))
        trs.append(tr)
        prev = b["c"]
        if i == n - 1:
            out[i] = sum(trs) / n
        elif i >= n:
            out[i] = (out[i - 1] * (n - 1) + tr) / n
    return out


def limit_flags(bars: list[dict], i: int, pct: float) -> tuple[bool, bool]:
    """(sàn, trần) — so đóng cửa hôm trước; HOSE ±7 %, lấy 6,5 % để lệch làm tròn."""
    if i == 0:
        return False, False
    ref = bars[i - 1]["c"]
    if ref <= 0:
        return False, False
    return bars[i]["c"] <= ref * (1 - pct), bars[i]["c"] >= ref * (1 + pct)


def _slope_rel(closes: list[float]) -> float:
    n = len(closes)
    if n < 3:
        return 0.0
    xm = (n - 1) / 2
    ym = sum(closes) / n
    num = sum((k - xm) * (c - ym) for k, c in enumerate(closes))
    den = sum((k - xm) ** 2 for k in range(n))
    return (num / den) / ym if den and ym else 0.0


# ---------- trạng thái ----------

@dataclass
class TR:
    kind: str                    # "acc" | "dist"
    origin: str                  # "sc" | "bc" | "range"
    start: int
    lo: float
    hi: float
    phase: str = "A"
    climax_i: Optional[int] = None
    climax_vol: float = 0.0
    climax_spread: float = 0.0
    ar_i: Optional[int] = None
    st_i: list[int] = field(default_factory=list)
    spring_i: Optional[int] = None
    spring_low: float = 0.0
    spring_vol: float = 0.0
    spring_spread: float = 0.0
    spring_kind: str = ""
    tested: bool = False
    break_i: Optional[int] = None   # nến đầu tiên đóng ngoài biên (chờ 1–3 phiên đóng lại trong)
    sos_i: Optional[int] = None
    sos_vol: float = 0.0
    lps_i: Optional[int] = None
    lps_low: float = 0.0
    bu_i: Optional[int] = None
    ut_i: list[int] = field(default_factory=list)
    end: Optional[int] = None
    end_reason: str = ""
    touch_hi: int = 0
    touch_lo: int = 0
    _out: int = 0                # số nến liên tiếp đóng ngoài dung sai

    def age(self, i: int) -> int:
        return i - self.start

    def to_dict(self) -> dict:
        return {"kind": self.kind, "origin": self.origin, "start": self.start, "end": self.end, "lo": round(self.lo, 4),
                "hi": round(self.hi, 4), "phase": self.phase, "sc": self.climax_i, "ar": self.ar_i, "st": list(self.st_i),
                "spring": self.spring_i, "spring_kind": self.spring_kind, "sos": self.sos_i, "lps": self.lps_i,
                "bu": self.bu_i, "ut": list(self.ut_i), "end_reason": self.end_reason}


@dataclass
class Markup:
    """Sau khi TR tích lũy kết thúc lên trên: theo dõi LPS/BU và SOW phá đáy LPS."""
    tr: TR
    lps_low: float
    start: int
    down: bool = False           # True = markdown sau TR phân phối


class Result:
    def __init__(self, bars: list[dict]):
        self.bars = bars
        self.events: list[dict] = []
        self.trs: list[TR] = []
        self.tr: Optional[TR] = None
        self.markup: Optional[Markup] = None
        self.pending: Optional[TR] = None     # SC/BC đã có, chờ AR
        self.atr = atr_wilder(bars, CFG["atr_n"])

    def add(self, i: int, at: int, eid: str, **extra) -> dict:
        ev = {"i": i, "at": at, "d": self.bars[i]["d"], "id": eid, **extra}
        self.events.append(ev)
        return ev

    # ---- tiện ích ----
    def av(self, i: int) -> float:
        return avg_vol(self.bars, i, CFG["vol_n"])

    def phase(self) -> str:
        if self.tr:
            return self.tr.phase if self.tr.kind == "acc" else "PP"
        if self.markup:
            return "E↓" if self.markup.down else "E"
        return "-"


# ---------- phát hiện ----------

def _climax(bars, i, atr, av, cfg, kind: str) -> bool:
    """SC (kind=acc) hoặc BC (kind=dist)."""
    w = cfg["climax_win"]
    if i < w or not atr or av <= 0:
        return False
    b = bars[i]
    floor, ceil = limit_flags(bars, i, cfg["limit_pct"])
    if b["v"] < cfg["climax_vol"] * av:
        return False
    ref = bars[i - w]["c"]
    if kind == "acc":
        if ref <= 0 or (b["c"] / ref - 1) > -cfg["climax_drop"]:
            return False
        if is_bull(b) and body(b) > 0.2 * max(spread(b), 1e-9):
            return False                                   # nến đỏ hoặc doji
        if not floor and spread(b) < cfg["climax_spread"] * atr:
            return False
        return close_pos(b) >= cfg["sc_close_pos"]
    if ref <= 0 or (b["c"] / ref - 1) < cfg["climax_drop"]:
        return False
    if is_bear(b) and body(b) > 0.2 * max(spread(b), 1e-9):
        return False
    if not ceil and spread(b) < cfg["climax_spread"] * atr:
        return False
    return close_pos(b) <= 1 - cfg["sc_close_pos"]


def _range_origin(bars, i, cfg) -> Optional[tuple[float, float]]:
    """Sơ đồ #2: 20 phiên gần nhất đi ngang sau đợt giảm, chạm mỗi biên ≥ 2 lần, độ dốc nhỏ. Trả (lo, hi) hoặc None."""
    n, pw = cfg["range_win"], cfg["range_prior_win"]
    if i + 1 < n + pw:
        return None
    w = bars[i + 1 - n:i + 1]
    hi = max(x["h"] for x in w)
    lo = min(x["l"] for x in w)
    if lo <= 0:
        return None
    height = hi / lo - 1
    if not (cfg["range_height_min"] <= height <= cfg["range_height_max"]):
        return None
    prior = max(x["c"] for x in bars[i + 1 - n - pw:i + 1 - n])
    if prior < hi * (1 + cfg["range_prior_drop"]):
        return None                                        # không có đợt giảm dẫn vào vùng
    band = cfg["range_touch"] * (hi - lo)
    th = sum(1 for x in w if x["h"] >= hi - band)
    tl = sum(1 for x in w if x["l"] <= lo + band)
    if th < 2 or tl < 2:
        return None
    if abs(_slope_rel([x["c"] for x in w])) > cfg["range_slope"]:
        return None
    return lo, hi


def analyze(bars: list[dict], cfg: Optional[dict] = None) -> Result:
    """Quét tuần tự toàn chuỗi. Trả Result với events (mọi sự kiện + nhãn), trs, tr/markup hiện tại."""
    cfg = {**CFG, **(cfg or {})}
    R = Result(bars)
    if len(bars) < MIN_BARS:
        return R
    for i in range(MIN_BARS, len(bars)):
        _step(R, i, cfg)
    return R


def _step(R: Result, i: int, cfg: dict) -> None:
    bars, b = R.bars, R.bars[i]
    atr, av = R.atr[i], R.av(i)
    if not atr or av <= 0 or spread(b) <= 0:
        return
    floor, ceil = limit_flags(bars, i, cfg["limit_pct"])
    vr = b["v"] / av

    # --- nhãn nỗ lực/kết quả (độc lập TR) ---
    if vr >= cfg["er_vol"] and (body(b) / atr) / vr < cfg["er_ratio"]:
        R.add(i, i, "er_absorb", vol_ratio=vr, body_atr=body(b) / atr)
    if (i >= 4 and is_bull(b) and b["v"] < bars[i - 1]["v"] and b["v"] < bars[i - 2]["v"]
            and spread(b) < cfg["nd_spread"] * atr and bars[i - 1]["c"] > bars[i - 4]["c"]):
        R.add(i, i, "no_demand", vol_ratio=vr)

    # --- SC/BC đang chờ AR ---
    if R.pending is not None:
        p = R.pending
        k = i - p.climax_i
        acc = p.kind == "acc"
        # sụp tiếp qua đáy SC (hay vượt đỉnh BC) → không phải cao trào
        if (acc and b["c"] < p.lo * (1 - cfg["tr_tol"])) or (not acc and b["c"] > p.hi * (1 + cfg["tr_tol"])):
            R.pending = None
        elif k >= cfg["ar_max"]:
            w = bars[p.climax_i + 1:i + 1]
            if acc:
                j = max(range(len(w)), key=lambda t: w[t]["h"])
                ar_px = w[j]["h"]
                ok = ar_px >= p.lo * (1 + cfg["ar_pct"])
            else:
                j = min(range(len(w)), key=lambda t: w[t]["l"])
                ar_px = w[j]["l"]
                ok = ar_px <= p.hi * (1 - cfg["ar_pct"])
            R.pending = None
            if ok:
                p.ar_i = p.climax_i + 1 + j
                if acc:
                    p.hi = ar_px
                else:
                    p.lo = ar_px
                R.add(p.ar_i, i, "ar", lo=p.lo, hi=p.hi, kind=p.kind)
                R.tr, R.markup = p, None
                R.trs.append(p)
        return  # trong lúc chờ AR không xét gì khác

    tr = R.tr
    if tr is None:
        _no_tr(R, i, atr, av, vr, floor, cfg)
        return

    # --- trong TR ---
    acc = tr.kind == "acc"
    age = tr.age(i)
    tol = cfg["tr_tol"]
    lo_ok, hi_ok = tr.lo * (1 - tol), tr.hi * (1 + tol)

    # sự kiện phá biên có KL (SOS / SOW) — xét trước quy tắc thoát TR
    strong_up = (is_bull(b) and b["c"] > tr.hi and vr >= cfg["sos_vol"] and close_pos(b) >= cfg["sos_close_pos"]
                 and (ceil or body(b) >= cfg["sos_body"] * atr))
    strong_dn = (is_bear(b) and b["c"] < tr.lo and vr >= cfg["sos_vol"] and close_pos(b) <= 1 - cfg["sos_close_pos"]
                 and (floor or body(b) >= cfg["sos_body"] * atr))

    if acc:
        if strong_up and tr.sos_i is None and age >= cfg["tr_min"]:
            tr.sos_i, tr.sos_vol, tr.phase = i, b["v"], "D"
            R.add(i, i, "sos", vol_ratio=vr, body_atr=body(b) / atr, close_pos=close_pos(b), tr=tr.to_dict(),
                  stop=tr.hi - cfg["stop_atr"] * atr, target=_target(tr, age), age=age)
        elif b["c"] < tr.lo and _climax(bars, i, atr, av, cfg, "acc"):
            # cao trào bán DƯỚI vùng: vùng cũ thất bại, mở chu kỳ mới từ SC này (ưu tiên SC, không ghi SOW)
            _close_tr(R, tr, i, "down")
            _no_tr(R, i, atr, av, vr, floor, cfg)
            return
        elif strong_dn and age >= cfg["tr_min"] and tr.end_reason != "sow":
            # tích lũy thất bại: phá đáy có lực → coi như SOW (thoát) một lần, rồi TR kết thúc theo quy tắc 2 phiên
            tr.end_reason = "sow"
            R.add(i, i, "sow", ref=tr.lo, vol_ratio=vr, tr=tr.to_dict(), where="acc_fail")
    else:
        if strong_dn and age >= cfg["tr_min"]:
            R.add(i, i, "sow", ref=tr.lo, vol_ratio=vr, tr=tr.to_dict(), where="dist", stop=None)
            tr.phase = "D"
            tr.sos_i = i   # dùng chung ô: mốc SOW để tìm LPSY
            tr.sos_vol = b["v"]

    # quy tắc thoát TR: đóng ngoài dung sai 2 phiên liên tiếp. Ở giai đoạn D (đã có SOS/SOW) KHÔNG đóng vùng theo
    # hướng phá vỡ — giữ tới khi có LPS/LPSY hoặc quá lps_max phiên, để nhịp lùi được xét.
    breaking_dir = (b["c"] > hi_ok) if acc else (b["c"] < lo_ok)
    if (b["c"] > hi_ok or b["c"] < lo_ok) and not (tr.sos_i is not None and breaking_dir):
        tr._out += 1
    else:
        tr._out = 0
    d_done = tr.sos_i is not None and i - tr.sos_i >= cfg["lps_max"]
    if tr._out >= cfg["tr_exit_bars"] or age > cfg["tr_max"] or d_done:
        if d_done:
            reason = "up" if acc else "down"
        else:
            reason = "age" if age > cfg["tr_max"] else ("up" if b["c"] > hi_ok else "down")
        _close_tr(R, tr, i, reason)
        if not d_done:
            _no_tr(R, i, atr, av, vr, floor, cfg)   # nến kết thúc vùng có thể chính là SC/BC mới
        return

    # đếm chạm biên (Phase B)
    band = cfg["range_touch"] * (tr.hi - tr.lo)
    if b["h"] >= tr.hi - band:
        tr.touch_hi += 1
    if b["l"] <= tr.lo + band:
        tr.touch_lo += 1

    if acc:
        _acc_events(R, tr, i, atr, av, vr, floor, ceil, cfg)
    else:
        _dist_events(R, tr, i, atr, av, vr, floor, ceil, cfg)


def _close_tr(R: Result, tr: TR, i: int, reason: str) -> None:
    """Kết thúc vùng tại nến i; lên (tích lũy) → theo dõi markup, xuống (phân phối) → markdown."""
    tr.end, tr.end_reason = i, reason
    R.tr = None
    if reason == "up" and tr.kind == "acc":
        R.markup = Markup(tr, tr.lps_low if tr.lps_i is not None else tr.lo, i)
        tr.phase = "E"
    elif reason == "down" and tr.kind == "dist":
        R.markup = Markup(tr, tr.hi, i, down=True)
    else:
        R.markup = None


def _no_tr(R: Result, i: int, atr, av, vr, floor, cfg) -> None:
    """Không có vùng: SOW phá đáy LPS khi đang markup; SC/BC mở vùng mới (chờ AR); vùng gốc range."""
    bars, b = R.bars, R.bars[i]
    m = R.markup
    if m and (i - m.start > cfg["markup_max"]
              or (m.down and b["c"] > m.tr.hi) or (not m.down and b["c"] < m.tr.lo)):
        R.markup = None                       # quá hạn, hoặc giá đã đi ngược hẳn qua biên vùng cũ
    if _climax(bars, i, atr, av, cfg, "acc"):
        # SC đi trước SOW-phá-LPS: cùng một nến không thể vừa "thoát" vừa "cao trào bán"
        R.markup = None
        p = TR("acc", "sc", i, b["l"], b["h"], climax_i=i, climax_vol=b["v"], climax_spread=spread(b))
        R.pending = p
        R.add(i, i, "sc", vol_ratio=vr, low=b["l"], close_pos=close_pos(b), stop=b["l"] - cfg["stop_atr"] * atr)
        return
    if R.markup and not R.markup.down:
        m = R.markup
        if (b["c"] < m.lps_low and vr >= cfg["sos_vol"] and close_pos(b) <= 1 - cfg["sos_close_pos"]
                and (floor or body(b) >= cfg["sos_body"] * atr)):
            R.add(i, i, "sow", ref=m.lps_low, vol_ratio=vr, tr=m.tr.to_dict(), where="markup")
            R.markup = None
    if _climax(bars, i, atr, av, cfg, "dist"):
        p = TR("dist", "bc", i, b["l"], b["h"], climax_i=i, climax_vol=b["v"], climax_spread=spread(b))
        R.pending = p
        R.add(i, i, "bc", vol_ratio=vr, high=b["h"], close_pos=close_pos(b))
        return
    rng = _range_origin(bars, i, cfg)
    if rng:
        lo, hi = rng
        t = TR("acc", "range", i, lo, hi, phase="B")
        R.tr, R.markup = t, None
        R.trs.append(t)


def _target(tr: TR, age: int) -> dict:
    h = tr.hi - tr.lo
    return {"min": round(tr.hi + h, 4), "ext": round(tr.hi + h * max(1.0, age / 20), 4)}


def _acc_events(R: Result, tr: TR, i: int, atr, av, vr, floor, ceil, cfg) -> None:
    bars, b = R.bars, R.bars[i]
    age = tr.age(i)
    after_ar = tr.ar_i is None or i > tr.ar_i

    # ST: về gần đáy SC với KL và spread nhỏ hơn SC (TR gốc range: KL ≤ 0,8× TB)
    if (after_ar and tr.phase in ("A", "B") and b["l"] <= tr.lo * (1 + cfg["st_near"]) and b["c"] >= tr.lo
            and len(tr.st_i) < 3):
        small = (b["v"] < cfg["st_vol"] * tr.climax_vol and spread(b) < tr.climax_spread) if tr.climax_vol else vr <= 0.8
        if small and (not tr.st_i or i - tr.st_i[-1] >= 5):
            tr.st_i.append(i)
            if tr.phase == "A":
                tr.phase = "B"
            R.add(i, i, "st", vol_ratio=vr, tr=tr.to_dict())
    if tr.phase == "A" and tr.touch_hi >= 2 and tr.touch_lo >= 2:
        tr.phase = "B"

    # Spring: phá đáy rồi đóng lại trong vùng (cùng phiên, hoặc 1–3 phiên sau khi đóng dưới đáy)
    if tr.sos_i is None:
        spring_now = b["l"] < tr.lo and b["c"] > tr.lo
        if b["c"] <= tr.lo:
            if tr.break_i is None:
                tr.break_i = i
        elif tr.break_i is not None and i - tr.break_i <= cfg["spring_recover_bars"]:
            spring_now = True
        if spring_now and age >= cfg["tr_min"] and (tr.spring_i is None or i - tr.spring_i > cfg["test_max"]):
            j0 = tr.break_i if tr.break_i is not None else i
            w = bars[j0:i + 1]
            low = min(x["l"] for x in w)
            vmax = max(x["v"] for x in w)
            smax = max(spread(x) for x in w)
            brk = (tr.lo - low) / tr.lo
            if brk <= cfg["spring1_break"]:
                if brk < cfg["spring3_break"] and vmax <= cfg["spring3_vol"] * av and close_pos(b) >= cfg["spring_close_pos"]:
                    kind = "spring3"
                elif brk < cfg["spring2_break"]:
                    kind = "spring2"
                else:
                    kind = "spring1"
                tr.spring_i, tr.spring_low, tr.spring_vol, tr.spring_spread, tr.spring_kind = i, low, vmax, smax, kind
                tr.tested = False
                tr.phase = "C"
                R.add(i, i, kind, break_pct=brk, vol_ratio=vmax / av, low=low, close_pos=close_pos(b), tr=tr.to_dict(),
                      stop=low - cfg["stop_atr"] * atr, target=_target(tr, age), age=age)
        if b["c"] > tr.lo:
            tr.break_i = None

        # Test sau Spring #1/#2: về gần đáy spring, KL < ½ KL spring, spread hẹp, đóng nửa trên, giữ trên đáy spring
        if (tr.spring_i is not None and not tr.tested and tr.spring_kind in ("spring1", "spring2")
                and cfg["test_min"] <= i - tr.spring_i <= cfg["test_max"]
                and b["l"] >= tr.spring_low and b["l"] <= tr.lo * (1 + cfg["st_near"])
                and b["v"] < cfg["test_vol"] * tr.spring_vol and spread(b) <= cfg["test_spread"] * tr.spring_spread
                and close_pos(b) >= cfg["test_close_pos"]):
            tr.tested = True
            R.add(i, i, "test", vol_ratio=vr, spring=tr.spring_kind, low=b["l"], tr=tr.to_dict(),
                  stop=tr.spring_low - cfg["stop_atr"] * atr, target=_target(tr, age), age=age)

        # UT trong vùng tích lũy: phá biên trên rồi đóng lại, KL cao, đóng gần đáy
        if b["h"] > tr.hi and b["c"] < tr.hi and vr >= cfg["ut_vol"] and close_pos(b) < cfg["ut_close_pos"]:
            tr.ut_i.append(i)
            R.add(i, i, "ut", vol_ratio=vr, tr=tr.to_dict())
        return

    # --- sau SOS (giai đoạn D): LPS / BU ---
    k = i - tr.sos_i
    if tr.lps_i is None and cfg["lps_min"] <= k <= cfg["lps_max"]:
        seg = bars[tr.sos_i:i]                           # từ nến SOS tới trước hôm nay
        if len(seg) >= 2:
            peak = max(range(len(seg)), key=lambda t: seg[t]["h"])   # đỉnh sau SOS (có thể là chính nến SOS)
            pull = seg[peak + 1:]                          # nhịp lùi = các nến sau đỉnh
            if pull:
                p_low = min(x["l"] for x in pull)
                p_hi = max(x["h"] for x in pull)
                p_v = sum(x["v"] for x in pull) / len(pull)
                hold = tr.hi - cfg["lps_depth"] * (tr.hi - tr.lo)
                if (p_low >= hold and all(x["v"] < tr.sos_vol for x in pull) and p_v <= cfg["lps_vol"] * av
                        and is_bull(b) and b["c"] > p_hi):
                    tr.lps_i, tr.lps_low = i, p_low
                    R.add(i, i, "lps", vol_ratio=vr, low=p_low, pull_bars=len(pull), tr=tr.to_dict(),
                          stop=p_low - cfg["stop_atr"] * atr, target=_target(tr, age), age=age)
                    _close_tr(R, tr, i, "up")          # vùng xong việc: sang markup, theo dõi SOW phá đáy LPS
                    return
    if (tr.lps_i is None and tr.bu_i is None and 2 <= k <= cfg["lps_max"] and i >= 2
            and tr.hi * (1 - cfg["bu_band"]) <= b["l"] <= tr.hi * (1 + cfg["bu_band"])
            and b["v"] < bars[i - 1]["v"] < bars[i - 2]["v"] and vr <= 1.0):
        tr.bu_i = i
        R.add(i, i, "bu", vol_ratio=vr, low=b["l"], tr=tr.to_dict(), stop=tr.hi * (1 - cfg["bu_band"]) - cfg["stop_atr"] * atr,
              target=_target(tr, age), age=age)


def _dist_events(R: Result, tr: TR, i: int, atr, av, vr, floor, ceil, cfg) -> None:
    bars, b = R.bars, R.bars[i]
    age = tr.age(i)
    after_ar = tr.ar_i is None or i > tr.ar_i
    if (after_ar and tr.phase in ("A", "B") and b["h"] >= tr.hi * (1 - cfg["st_near"]) and b["c"] <= tr.hi
            and len(tr.st_i) < 3):
        small = b["v"] < cfg["st_vol"] * tr.climax_vol and spread(b) < tr.climax_spread
        if small and (not tr.st_i or i - tr.st_i[-1] >= 5):
            tr.st_i.append(i)
            if tr.phase == "A":
                tr.phase = "B"
            R.add(i, i, "st", vol_ratio=vr, tr=tr.to_dict(), side="top")
    if tr.sos_i is None:
        if b["h"] > tr.hi and b["c"] < tr.hi and vr >= 1.0:
            brk = (b["h"] - tr.hi) / tr.hi
            eid = "utad" if (age >= cfg["tr_min"] and brk <= cfg["utad_break"]) else "ut"
            if not tr.ut_i or i - tr.ut_i[-1] >= 3:
                tr.ut_i.append(i)
                if eid == "utad":
                    tr.phase = "C"
                R.add(i, i, eid, break_pct=brk, vol_ratio=vr, close_pos=close_pos(b), tr=tr.to_dict())
        return
    # sau SOW: LPSY = hồi phục yếu (KL ≤ 0,8×, không vượt lại đáy vùng), nến giảm chốt
    k = i - tr.sos_i
    if tr.lps_i is None and 2 <= k <= cfg["lps_max"] and is_bear(b) and b["h"] <= tr.lo * (1 + cfg["bu_band"]):
        seg = bars[tr.sos_i + 1:i]
        if seg and max(x["h"] for x in seg) <= tr.lo * (1 + cfg["bu_band"]) and sum(x["v"] for x in seg) / len(seg) <= cfg["lps_vol"] * av:
            tr.lps_i = i
            R.add(i, i, "lpsy", vol_ratio=vr, tr=tr.to_dict())
            _close_tr(R, tr, i, "down")


# ---------- giao diện cho job / measure ----------

def signals_at(R: Result, i: int) -> list[dict]:
    """Sự kiện phát hiện tại nến i (at == i), bỏ nhãn; sắp theo priority."""
    out = [e for e in R.events if e["at"] == i and EVENTS[e["id"]]["direction"] != "label"]
    return sorted(out, key=lambda e: EVENTS[e["id"]]["priority"])


def board_state(R: Result, i: int) -> dict:
    """Trạng thái mã cho tab Bảng tại nến cuối: giai đoạn, biên vùng, tuổi, sự kiện gần nhất."""
    tr = R.tr or (R.markup.tr if R.markup else None)
    last = next((e for e in reversed(R.events) if EVENTS[e["id"]]["direction"] != "label"), None)
    st = {"phase": R.phase(), "tr": tr.to_dict() if tr else None, "tr_age": tr.age(i) if R.tr else None,
          "last_event": last["id"] if last else None, "last_event_date": last["d"].isoformat() if last else None}
    return st


def relative_strength(bars: list[dict], idx_bars: list[dict], n: int = 20) -> Optional[float]:
    """rs_n = (c/c[-n]) / (idx/idx[-n]) − 1 theo ngày khớp nhau. None nếu thiếu dữ liệu."""
    if len(bars) <= n:
        return None
    idx = {b["d"]: b["c"] for b in idx_bars}
    d1, d0 = bars[-1]["d"], bars[-1 - n]["d"]
    if d1 not in idx or d0 not in idx or not idx[d0] or not bars[-1 - n]["c"]:
        return None
    return (bars[-1]["c"] / bars[-1 - n]["c"]) / (idx[d1] / idx[d0]) - 1
