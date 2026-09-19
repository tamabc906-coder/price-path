# LightGBM xác suất hướng — walk-forward 2021–2026 · 39 mã · 2026-09-20

Tham số: 15 lá, min_data_in_leaf 200, lr 0.03, 300 vòng, 27 đặc trưng, purge 35 ngày. Cổng: Brier < tần suất ô VÀ acc > luôn-tăng ở ≥ 4/5 năm trọn.

## h = 5 phiên — TẮT (Brier thắng 0/5, acc thắng 1/5, cần 4)

| Năm | test | tăng thật | acc LGBM | acc luôn-tăng | Brier LGBM | Brier ô | Brier toàn cục | Brier 0,5 | p90 của P | đặc trưng mạnh |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2021 | 9,493 | 57.2 % | 51.0 % ✗ | 57.2 % | 0.2534 ✗ | 0.2490 | 0.2509 | 0.2500 | 0.601 | vol20_rank, upvol_share, dd_from_high60, atr_pct |
| 2022 | 9,698 | 45.7 % | 49.6 % ✓ | 45.7 % | 0.2605 ✗ | 0.2517 | 0.2519 | 0.2500 | 0.692 | upvol_share, vol20_rank, r20, ema50_pos |
| 2023 | 9,711 | 56.6 % | 49.5 % ✗ | 56.6 % | 0.2537 ✗ | 0.2521 | 0.2492 | 0.2500 | 0.577 | vol20_rank, upvol_share, dd_from_high60, r20 |
| 2024 | 9,750 | 50.1 % | 50.0 % ✗ | 50.1 % | 0.2520 ✗ | 0.2502 | 0.2502 | 0.2500 | 0.569 | vol20_rank, dd_from_high60, upvol_share, vol20 |
| 2025 | 9,711 | 53.4 % | 51.6 % ✗ | 53.4 % | 0.2511 ✗ | 0.2501 | 0.2492 | 0.2500 | 0.583 | vol20_rank, vol20, dd_from_high60, upvol_share |
| 2026* | 6,786 | 42.9 % | 49.2 % ✓ | 42.9 % | 0.2526 ✓ | 0.2537 | 0.2527 | 0.2500 | 0.564 | vol20_rank, vol20, dd_from_high60, atr_pct |

## h = 10 phiên — TẮT (Brier thắng 1/5, acc thắng 1/5, cần 4)

| Năm | test | tăng thật | acc LGBM | acc luôn-tăng | Brier LGBM | Brier ô | Brier toàn cục | Brier 0,5 | p90 của P | đặc trưng mạnh |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2021 | 9,493 | 59.3 % | 51.9 % ✗ | 59.3 % | 0.2527 ✗ | 0.2475 | 0.2472 | 0.2500 | 0.644 | vol20_rank, atr_pct, dd_from_high60, upvol_share |
| 2022 | 9,698 | 44.5 % | 47.4 % ✓ | 44.5 % | 0.2767 ✗ | 0.2570 | 0.2563 | 0.2500 | 0.788 | atr_pct, ema50_pos, vol20, vol20_rank |
| 2023 | 9,711 | 59.8 % | 50.3 % ✗ | 59.8 % | 0.2532 ✗ | 0.2502 | 0.2459 | 0.2500 | 0.606 | vol20_rank, dd_from_high60, ema50_pos, atr_pct |
| 2024 | 9,750 | 50.1 % | 49.7 % ✗ | 50.1 % | 0.2521 ✗ | 0.2505 | 0.2511 | 0.2500 | 0.595 | dd_from_high60, vol20_rank, atr_pct, vol20 |
| 2025 | 9,711 | 55.6 % | 53.1 % ✗ | 55.6 % | 0.2493 ✓ | 0.2496 | 0.2474 | 0.2500 | 0.616 | vol20_rank, dd_from_high60, vol20, atr_pct |
| 2026* | 6,786 | 42.3 % | 47.6 % ✓ | 42.3 % | 0.2550 ✓ | 0.2567 | 0.2564 | 0.2500 | 0.585 | vol20_rank, vol20, dd_from_high60, atr_pct |

(*) năm chưa trọn, không tính vào cổng.

## Quyết định: **TẮT** — app dùng tần suất ô chế độ cho P(tăng).
