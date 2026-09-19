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

## Kết quả đo (tái lập bằng script trong `scripts/`)

- `measure_features.py` → `reports/measure-20-phien-2026-09-19.md`: trong 20 phiên quá khứ, **khối lượng** là thứ có
  tín hiệu nhất quán (KL dồn phiên tăng, KL ≥2×: 7–8/11 năm hơn mua-đại); VN-Index "tăng" chỉ 2/11 → bỏ trục;
  ST×EMA10 4/11 → hạ cấp. Trục chế độ hiện tại: vol · upvol · st · spike · climax · gap.
- `evaluate.py` → `reports/eval-2026-09-19.md` (walk-forward 2021–2026, 54.369 hàng):
  - **Nón đúng cỡ:** coverage 80 % = 78–83 %, 90 % = 88–93 % ở **5/5 năm trọn** (h=10) — nhờ tự sửa cỡ; bản
    không sửa cỡ hụt nặng năm 2022 (68 %). **ĐẠT** ngưỡng kế hoạch.
  - **Ô chế độ gần như không làm nón hẹp hơn:** pinball 1,894 vs nón ngây thơ (pool toàn cục × biến động) 1,901 —
    khác 0,4 %. Độ rộng nón đến từ biến động của mã, không phải từ nhãn chế độ.
  - **P(tăng) từ tần suất ô: yếu.** Trung vị 0,55, chỉ 8,5 % hàng ≥ 0,60; thua "luôn tăng" ở năm bò; Brier hơn toàn
    cục 3/6 năm. Lệnh P ≥ 0,58 giữ 10 phiên: hơn mua-đại 4/6 năm nhưng chủ yếu "đỡ lỗ hơn" ở năm xấu.
  - Coverage theo ngày dao động mạnh (39 mã cùng phiên tương quan): cửa sổ 20 phiên chỉ 8–38 % số ngày nằm trong
    [76; 84]; cửa sổ **60 phiên** 42–53 % trong [76; 84] và ~75 % trong [72; 88] → tab Lịch sử chấm bằng cửa sổ 60
    phiên, dải chấp nhận ±6 điểm.

- `train_direction.py` → `reports/walkforward-2026-09-20.md` (+ bản `-khong-vnindex.md`): **LightGBM TẮT.**
  Brier 0,25–0,28 (tệ hơn tung xu), thắng tần suất ô 0–1/5 năm. Mô hình bám vào đặc trưng VN-Index (39 mã cùng
  ngày cùng giá trị → ~250 mẫu độc lập/năm) rồi áp chế độ năm cũ sang năm mới (2023 đúng 42,8 %). Bỏ nhóm VN-Index
  cũng chỉ về ~0,25, không thắng. Booster không ghi khi cổng tắt; `gate.json` giữ bảng để giao diện hiển thị.
  Kết luận: **hướng 5–10 phiên tới không dự đoán được** bằng dữ liệu giá/KL ở cấp mã — app hiện P(tăng) = tần suất
  ô và nói rõ nó gần mốc chung.

## Tiến độ

- [x] **G0** (19/09/2026): khung dự án, venv, kho lịch sử 40 mã, 7 test.
- [x] **G1** (19/09/2026): `model/features.py`, `regime.py`, `cone.py`, `conformal.py`, `scripts/evaluate.py`; 14 test; ĐẠT ngưỡng coverage.
- [x] **G2** (20/09/2026): `model/direction.py`, `scripts/train_direction.py`; cổng TẮT; 17 test.
- [ ] G3: job daily + GitHub Actions.
- [ ] G4: PWA + push.
- [ ] G5: chạy thật 1 tuần, so coverage.
