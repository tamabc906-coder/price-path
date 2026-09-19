"""Cấu hình chung. Mọi thứ qua biến môi trường: local đọc .env, GitHub Actions đọc Secrets.

Chép khuôn candle-radar/common/config.py, thêm HISTORY (kho nến dài hạn) và HORIZONS.
"""
from __future__ import annotations

import os
from datetime import timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
# JSON mà giao diện tĩnh đọc — nằm trong docs/ vì GitHub Pages phục vụ thư mục /docs.
SITE_DATA = ROOT / "docs" / "data"
# Kho nến ngày đầy đủ (39 mã + VNINDEX, ~7 năm) — commit trong repo, job chỉ nối thêm nến mới.
HISTORY = ROOT / "data" / "history.json"
ARTIFACTS = ROOT / "model" / "artifacts"

# utf-8-sig: Notepad/PowerShell ghi BOM ở đầu file; thiếu cái này thì biến đầu tiên thành
# "﻿VAPID_PUBLIC_KEY" và thông báo im lặng không bao giờ tới (bài học KingStock).
load_dotenv(ROOT / ".env", encoding="utf-8-sig")

# Offset cố định +7: VN không có giờ mùa hè, Windows mặc định thiếu bộ tzdata.
TZ = timezone(timedelta(hours=7), name="Asia/Ho_Chi_Minh")

# Số phiên dự báo tới: nón xác suất và P(tăng) tính tại các mốc này (đếm PHIÊN, không phải ngày lịch).
HORIZONS = (5, 10, 20)
INDEX_SYMBOL = "VNINDEX"

HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "30"))
DNSE_BASE = os.getenv("DNSE_BASE", "https://services.entrade.com.vn/chart-api/v2/ohlcs")

# Danh mục lấy từ KingStock (app cảnh báo Stochastic đang chạy trên Fly). API này công khai,
# trả cả company_name và exchange. Fly chết thì job dùng bản chụp docs/data/watchlist.json.
KINGSTOCK_WATCHLIST = os.getenv("KINGSTOCK_WATCHLIST", "https://kingstock-deptlink.fly.dev/api/watchlist")

VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:admin@example.com")

# Cloudflare Worker nhận đăng ký push + cài đặt (tuỳ chọn). Để trống = dùng fallback.
WORKER_URL = os.getenv("WORKER_URL", "").rstrip("/")
WORKER_TOKEN = os.getenv("WORKER_TOKEN", "")
PUSH_SUBS_FALLBACK = os.getenv("PUSH_SUBS_FALLBACK", "")

# Header giả trình duyệt — một số nguồn có WAF chặn UA lạ.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}
