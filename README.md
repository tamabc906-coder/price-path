# Price Path — nón xác suất đường đi giá cổ phiếu VN

Dự án chứng khoán thứ 8 (sau KingStock, candle-radar, TuDoanh Radar…). App **không vẽ một đường giá duy
nhất** — nó trả về, cho mỗi mã trong danh mục KingStock (39 mã), sau mỗi phiên:

- **Nón xác suất**: vùng giá 50 / 80 / 90 % cho 5, 10, 20 phiên tới, có điều kiện theo *chế độ thị trường*
  hiện tại (Supertrend, vị trí so EMA, mức biến động, cờ "trần + bùng nổ khối lượng + phá đỉnh", xu hướng VN-Index).
- **Xác suất tăng** P(đóng cửa sau 5/10 phiên > hôm nay): tần suất lịch sử theo chế độ; LightGBM chỉ được
  bật khi walk-forward thắng mốc "luôn tăng" ≥ 4/5 năm (mặc định tắt).
- **Tự chấm điểm**: mỗi phiên chấm lại xem giá thật có nằm trong nón đã dự báo không (coverage), hệ số
  giãn nón tự điều chỉnh (adaptive conformal). Con số coverage hiện ngay trên trang để người dùng biết
  nón đang đúng tới đâu.

**Không hứa** dự đoán chính xác giá, không hứa chỉ báo có "edge" bền vững. Kỳ vọng thật cho P(tăng): 52–58 %.
Cơ sở nghiên cứu và thiết kế chi tiết: `C:\Users\IT\.claude\plans\b-n-l-m-t-trader-gentle-wall.md`.

Hạ tầng đúng khuôn candle-radar: GitHub Actions chạy job sau ATC (15:40 T2–T6), GitHub Pages phục vụ
`docs/` (PWA), Web Push tới điện thoại. Không máy chủ.

## Chạy local

```
install.bat                                    # tạo venv, cài thư viện (một lần)
venv\Scripts\python -m scripts.fetch_history   # tải trọn lịch sử vào data/history.json (một lần)
venv\Scripts\python -m pytest -q
```

## Dữ liệu

- Nguồn: DNSE/Entrade (`common/dnse.py`), miễn phí, không token. Giá **nghìn đồng, đã điều chỉnh cổ tức**
  (giữ nguyên — lợi suất log cần chuỗi liên tục). Chỉ số qua endpoint `/index`.
- Kho `data/history.json` (`common/store.py`): 39 mã + VNINDEX, commit trong repo. Job hằng ngày chỉ lấy
  30 ngày gần nhất rồi nối vào kho; mã mới vào danh mục thì tải trọn lịch sử.
- **Giới hạn DNSE đo ngày 19/09/2026:** cổ phiếu lùi tới **2012-03-26** (HPG 3.614 nến), VN-Index tới
  **2004-10-25**. Kho hiện lấy mốc 4.000 ngày → từ **2015-10-08**, ~2.730 nến/mã, 4,6 MB. Mã lên sàn
  muộn ngắn hơn: MSB từ 12/2020 (1.429 nến), SZC 01/2019, TCB 06/2018, GVR 03/2018. Muốn xa hơn:
  `python -m scripts.fetch_history --refresh --days 8000`.
- Danh mục: `job/watchlist.py` đọc API KingStock, bản chụp `docs/data/watchlist.json` khi Fly ngủ.

## Bẫy đã gặp, đừng dẫm lại (thừa kế từ candle-radar / KingStock)

1. DNSE trả nến hôm nay dừng giữa phiên (~13:45) với HTTP 200 → chỉ tin nến hôm nay khi chuỗi nến 1' đã có
   ATC 14:45 (`dnse.session_settled`). `fetch_history` chạy trước 15:30 sẽ bỏ nến hôm nay.
2. Mã ít thanh khoản mang nến cũ nhiều ngày → `stale`, không dự báo.
3. Console Windows cp1252 → `sys.stdout.reconfigure(encoding="utf-8")` trước khi in tiếng Việt.
4. Python trên Windows không hiểu đường dẫn `/c/...` của Git Bash — dùng `C:\...`.
5. 39 mã là danh mục chọn *hôm nay* → mọi thống kê lịch sử có survivorship bias; tần suất tăng lịch sử
   của nhóm này cao hơn thị trường, nên mốc "luôn tăng" khó thắng — đó là chủ đích.

## Tiến độ

- [x] **G0** (19/09/2026): khung dự án, venv, kho lịch sử 40 mã, 7 test.
- [ ] G1: đặc trưng, chế độ, nón bootstrap, conformal, `scripts/evaluate.py` + báo cáo coverage theo năm.
- [ ] G2: LightGBM walk-forward + gate.
- [ ] G3: job daily + GitHub Actions.
- [ ] G4: PWA + push.
- [ ] G5: chạy thật 1 tuần, so coverage.
