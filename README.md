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
run-daily-local.bat --dry-run                  # xem dự báo hôm nay, không ghi gì (~35 s)
run-daily-local.bat                            # ghi docs/data/*.json, không push
venv\Scripts\python -m scripts.backfill --sessions 90 --yes   # chạy lại 90 phiên: mồi hệ số giãn + sổ chấm (4 phút)
```

## Job hằng ngày (`job/run_daily.py`, GitHub Actions 15:40 T2–T6)

1. Danh mục KingStock → 30 ngày nến DNSE gần nhất + VNINDEX → nối vào kho `data/history.json` (mã mới → tải trọn).
2. Nguồn chưa chốt (≥ 20 % mã thanh khoản thiếu nến ATC 14:45) → không ghi gì, cron dự phòng 16:10/16:50/18:15 thử lại.
3. **Chấm điểm trước, dự báo sau:** nón phát 5/10/20 phiên trước (file `docs/data/daily/<ngày>.json`) đến hạn → tỷ lệ
   mã trúng → cập nhật hệ số giãn (`model/artifacts/conformal_state.json`). Rồi mới dựng nón hôm nay.
4. Mỗi mã: ô chế độ → pool → 2.000 đường bootstrap (seed theo mã+ngày, chạy lại ra cùng nón) → phân vị 5…95 tại
   +5/+10/+20 → giãn theo s → giá; P(tăng) = tần suất ô (LightGBM chỉ khi `gate.json` bật); 2 kịch bản A/B.
5. Push mã có `p10 ≥ p_min` (0,58) và `n ≥ n_min` (200); > 6 mã → một thông báo tổng hợp. Cài đặt: `docs/data/settings.json`.
6. Ghi `latest.json` (bảng 39 mã + verdict + lịch sử), `bars.json` (60 nến/mã), `daily/<ngày>.json`, `state.json`.
   Bot commit `docs/data/ data/history.json model/artifacts/conformal_state.json [skip ci]`.

**Verdict "đúng cỡ":** coverage nón 80 % tại +10 phiên, cửa sổ **60 phiên**, dải 74–86 %. (20 phiên dao động quá mạnh
vì 39 mã cùng ngày tương quan — evaluate cho thấy 60 phiên nằm trong dải ~75 % số ngày.)

## Giao diện (`docs/`, GitHub Pages)

JS thuần, không thư viện; đọc `data/latest.json` + `data/bars.json` (`cache: no-cache`, SW ép `reload`). Tab **Hôm nay**:
thẻ mỗi mã = giá · chip chế độ · nón SVG (28 nến + dải 50/80/90 % + trung vị + kịch bản A/B) · P(tăng) 5p/10p kèm
**mốc chung** · n mẫu; mã qua ngưỡng lên đầu. **Biểu đồ**: nón lớn có dải KL, bảng phân vị, "vì sao nón có hình này".
**Sổ chấm**: ô lớn verdict 60 phiên, dải 30 ô rộng/đúng/hẹp, bảng từng phiên. **Cài đặt**: đăng ký push (dán Secret),
ngưỡng (chỉ đọc), bảng cổng LightGBM, hệ số giãn, hệ thống. Sửa app.js/styles.css → tăng `?v=` trong `index.html`
và bảo người dùng đóng hẳn app (PWA giữ bản cũ). Chụp thử: `python -m http.server -d docs 8765` + Chrome headless
bọc iframe 420 px (Chrome không cho cửa sổ < 500 px).

## Đưa lên GitHub (làm một lần, trên web vì máy không có `gh`)

1. Tạo repo public `price-path` → `git remote add origin …` → `git push -u origin master:main`.
2. Settings → Pages: branch `main`, folder `/docs`.
3. `venv\Scripts\python -m job.gen_vapid` → dán 3 dòng vào Settings → Secrets and variables → Actions
   (`VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`); `PUSH_SUBS_FALLBACK` thêm sau khi điện thoại đăng ký (G4).
   Chưa có VAPID thì job vẫn chạy, chỉ bỏ qua push (`state.push.errors = ["Thiếu khoá VAPID"]`).
4. Actions → daily → Run workflow để chạy lần đầu; xem `docs/data/latest.json` trên Pages.

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

## Vùng giá — mô-đun `zone/` (độc lập, thêm 20/09/2026)

Chỉ báo riêng: gộp **từng lệnh khớp trong phiên** (giá · KL · Mua/Bán chủ động) theo mức giá, tích luỹ 10/20/40 phiên,
chỉ ra **POC**, **Value Area 70 %**, **vùng mua nhiều / bán nhiều** và lớp **lệnh lớn ≥ 500 tr đ** ("cá mập"). Tab
*Vùng giá* trong PWA; chạy tách biệt với job nón: `zone/run_daily.py`, workflow `zone.yml` (15:50 VN + dự phòng 16:25,
18:30 và **08:15 sáng hôm sau**), dữ liệu `data/zone/<MÃ>.json` + `docs/data/zone/`. Kế hoạch gốc:
`C:\Users\IT\.claude\plans\t-i-c-n-x-y-d-ng-toasty-rabbit.md`.

```
venv\Scripts\python -m zone.collect FPT            # in profile 1 phiên để đối chiếu app CTCK
venv\Scripts\python -m zone.backfill               # dựng tạm 47 phiên ước lượng từ nến 1' (đã chạy 20/09)
venv\Scripts\python -m zone.run_daily --dry-run    # ~1 phút cho 39 mã
venv\Scripts\python -m scripts.zone_check_sources FPT   # đối chiếu Mua/Bán với Vietcap (một lần)
```

- **Nguồn tick: VNDirect** `api-finfo.vndirect.com.vn/v4/stock_intraday_latest` (`common/vndirect.py`) — miễn phí,
  ~12 k tick/phiên/mã, 3 trang × 5.000. Chỉ giữ **phiên gần nhất** → mỗi ngày gom một phiên, cron sáng hôm sau vớt phiên
  hụt. Phải `sort=accumulatedVol:asc`: không có sort thì trang chồng/thiếu tuỳ lần gọi (FPT: 12.669 dòng mà chỉ 9.486
  tick khác nhau). Đủ phiên ⇔ Σ KL == accumulatedVol cuối, thiếu thì không ghi.
- **`side` của VNDirect đặt tên theo bên BỊ ĐỘNG**: `PB` = bán chủ động, `PS` = mua chủ động. Đối chiếu 1.497 lệnh
  FPT/HPG/VNM với Vietcap (khớp từng lệnh với app CTCK): đọc ngược đúng 100 %, đọc xuôi 0 %. Một lệnh chủ động bị tách
  thành nhiều tick → `collect.orders` gộp tick cùng giây/giá/hướng trước khi xét lệnh lớn.
- **Giá thô vs điều chỉnh**: tick là giá thô, kho nến DNSE là giá điều chỉnh (FPT 18/09: 71,7 vs 65,18). Hệ số
  `close_history / close_phiên` nhân vào mọi mức giá LÚC DỰNG profile (`zone/profile.py`), nên sự kiện sau khi lưu vẫn đúng.
- ATO/ATC không có hướng → nhóm `x`: tính vào tổng/POC, không vào tỷ lệ mua/bán (18/09 ETF cơ cấu, ATC FPT = 55 % KL).
- Lịch sử trước 18/09 là **ước lượng** từ nến 1' DNSE (`zone/backfill.py`: KL chia đều [l,h], hướng theo c−o) — giao diện
  tô nhạt, ghi `n_thật/n`. Phiên thật không bao giờ bị ghi đè.
- Chưa có push, chưa đo giá trị dự báo của vùng — thống kê mô tả. Ngưỡng ở `docs/data/zone/settings.json`.

## Bẫy đã gặp, đừng dẫm lại (thừa kế từ candle-radar / KingStock)

1. DNSE trả nến hôm nay dừng giữa phiên (~13:45) với HTTP 200 → chỉ tin nến hôm nay khi chuỗi nến 1' đã có
   ATC 14:45 (`dnse.session_settled`). `fetch_history` chạy trước 15:30 sẽ bỏ nến hôm nay.
2. Mã ít thanh khoản mang nến cũ nhiều ngày → `stale`, không dự báo.
3. Console Windows cp1252 → `sys.stdout.reconfigure(encoding="utf-8")` trước khi in tiếng Việt.
4. Python trên Windows không hiểu đường dẫn `/c/...` của Git Bash — dùng `C:\...`.
5. 39 mã là danh mục chọn *hôm nay* → mọi thống kê lịch sử có survivorship bias; tần suất tăng lịch sử
   của nhóm này cao hơn thị trường, nên mốc "luôn tăng" khó thắng — đó là chủ đích.
6. **`job/watchlist.load()` ghi lại `docs/data/watchlist.json`** mỗi lần gọi. Workflow phụ nào tái dùng nó mà chỉ
   `git add` thư mục riêng thì working tree bẩn → `git pull --rebase` từ chối → bước commit đỏ dù job đã chạy xong
   (`zone` đỏ 3/3 lần 21/09/2026, suýt mất phiên vì nguồn tick chỉ giữ một ngày). Dọn file đó trước khi `pull`.

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
- [x] **G3** (20/09/2026): `job/forecast.py`, `run_daily.py`, `push.py`, `settings.py`, `scripts/backfill.py`, workflow; backfill 90 phiên → coverage 60p = 78 %; 20 test. Chưa có remote GitHub.
- [x] **G4** (20/09/2026): PWA `docs/` 4 tab (Hôm nay · Biểu đồ · Sổ chấm · Cài đặt), nón SVG + 2 kịch bản, đăng ký push
  kiểu candle-radar (dán Secret). Chụp headless 420 px OK. Chờ: repo GitHub + Pages + VAPID vào `docs/config.js`.
- [ ] G5: chạy thật 1 tuần, so coverage.
- [x] **Zone** (20/09/2026): `common/vndirect.py`, `zone/{collect,store,backfill,profile,run_daily}.py`, `zone.yml`,
  tab Vùng giá (`?v=2`), 14 test; 39 mã đã có 47 phiên ước lượng + phiên thật 18/09. Chờ: workflow chạy 15:50 T2 22/09.
