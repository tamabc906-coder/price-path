# LightGBM xác suất hướng — walk-forward 2021–2026 · 39 mã · 2026-09-20

Tham số: 15 lá, min_data_in_leaf 200, lr 0.03, 300 vòng, 32 đặc trưng, purge 35 ngày. Cổng: Brier < tần suất ô VÀ acc > luôn-tăng ở ≥ 4/5 năm trọn.

## h = 5 phiên — TẮT (Brier thắng 0/5, acc thắng 2/5, cần 4)

| Năm | test | tăng thật | acc LGBM | acc luôn-tăng | Brier LGBM | Brier ô | Brier toàn cục | Brier 0,5 | p90 của P | đặc trưng mạnh |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2021 | 9,493 | 57.2 % | 51.8 % ✗ | 57.2 % | 0.2536 ✗ | 0.2490 | 0.2509 | 0.2500 | 0.661 | idx_vol20, idx_r20, idx_r5, vol20_rank |
| 2022 | 9,698 | 45.7 % | 47.4 % ✓ | 45.7 % | 0.2763 ✗ | 0.2517 | 0.2519 | 0.2500 | 0.673 | idx_vol20, idx_r20, idx_r5, idx_above_ema50 |
| 2023 | 9,711 | 56.6 % | 44.2 % ✗ | 56.6 % | 0.2726 ✗ | 0.2521 | 0.2492 | 0.2500 | 0.593 | idx_vol20, idx_r20, idx_r5, idx_above_ema50 |
| 2024 | 9,750 | 50.1 % | 50.7 % ✓ | 50.1 % | 0.2536 ✗ | 0.2502 | 0.2502 | 0.2500 | 0.580 | idx_vol20, idx_r20, idx_r5, dd_from_high60 |
| 2025 | 9,711 | 53.4 % | 50.7 % ✗ | 53.4 % | 0.2529 ✗ | 0.2501 | 0.2492 | 0.2500 | 0.628 | idx_vol20, idx_r20, idx_r5, dd_from_high60 |
| 2026* | 6,786 | 42.9 % | 52.4 % ✓ | 42.9 % | 0.2511 ✓ | 0.2537 | 0.2527 | 0.2500 | 0.592 | idx_vol20, idx_r20, idx_r5, idx_above_ema50 |

## h = 10 phiên — TẮT (Brier thắng 1/5, acc thắng 3/5, cần 4)

| Năm | test | tăng thật | acc LGBM | acc luôn-tăng | Brier LGBM | Brier ô | Brier toàn cục | Brier 0,5 | p90 của P | đặc trưng mạnh |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2021 | 9,493 | 59.3 % | 49.7 % ✗ | 59.3 % | 0.2589 ✗ | 0.2475 | 0.2472 | 0.2500 | 0.696 | idx_vol20, idx_r20, idx_r5, vol20_rank |
| 2022 | 9,698 | 44.5 % | 47.1 % ✓ | 44.5 % | 0.2833 ✗ | 0.2570 | 0.2563 | 0.2500 | 0.791 | idx_vol20, idx_r20, idx_r5, vol20_rank |
| 2023 | 9,711 | 59.8 % | 42.8 % ✗ | 59.8 % | 0.2724 ✗ | 0.2502 | 0.2459 | 0.2500 | 0.633 | idx_vol20, idx_r20, idx_r5, idx_above_ema50 |
| 2024 | 9,750 | 50.1 % | 52.4 % ✓ | 50.1 % | 0.2536 ✗ | 0.2505 | 0.2511 | 0.2500 | 0.619 | idx_vol20, idx_r20, idx_r5, vol20_rank |
| 2025 | 9,711 | 55.6 % | 56.3 % ✓ | 55.6 % | 0.2447 ✓ | 0.2496 | 0.2474 | 0.2500 | 0.660 | idx_vol20, idx_r20, idx_r5, idx_above_ema50 |
| 2026* | 6,786 | 42.3 % | 50.0 % ✓ | 42.3 % | 0.2612 ✗ | 0.2567 | 0.2564 | 0.2500 | 0.622 | idx_vol20, idx_r20, idx_r5, idx_above_ema50 |

(*) năm chưa trọn, không tính vào cổng.

## Quyết định: **TẮT** — app dùng tần suất ô chế độ cho P(tăng).
