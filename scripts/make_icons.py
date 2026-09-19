r"""Vẽ PNG icon PWA từ toạ độ logo (docs/icons/logo.svg) — không cần cairosvg. Chép khuôn candle-radar.
Chạy: venv\Scripts\python -m scripts.make_icons   (cần Pillow, chỉ dùng trên máy dev; Actions không gọi).

Logo: monogram P — thân chữ P vàng, bụng chữ P là ba lớp nón lồng nhau mở sang phải (nhạt → đậm),
trung vị nét đứt kem. Nền tím đậm để khác candle-radar / Candle Watch (xanh rêu) trên màn hình điện thoại.
"""
from pathlib import Path

from PIL import Image, ImageDraw

PURPLE, GOLD, CREAM = (0x3B, 0x2A, 0x6B), (0xE3, 0xB5, 0x4D), (0xF7, 0xF4, 0xEC)
OUT = Path(__file__).resolve().parent.parent / "docs" / "icons"


def _mix(a, b, t):
    """Màu a phủ lên b với độ mờ t (thay cho fill-opacity của SVG)."""
    return tuple(int(x * t + y * (1 - t)) for x, y in zip(a, b))


def draw(size: int, maskable: bool) -> Image.Image:
    # Vẽ ở 4× rồi thu nhỏ để nét mượt. Maskable: nền phủ kín, hình thu vào vùng an toàn 80 %.
    S = size * 4
    img = Image.new("RGBA", (S, S), PURPLE if maskable else (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if not maskable:
        d.rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 28 / 120), fill=PURPLE)
    k = (S * 0.8 / 120) if maskable else (S / 120)
    off = (S - 120 * k) / 2

    def P(x, y):
        return (off + x * k, off + y * k)

    def bowl(x_right, y1, y2, col):
        # Hình chữ D: chữ nhật + nửa tròn bên phải, bán kính = nửa chiều cao; trái kéo dài dưới thân P.
        r = (y2 - y1) / 2
        x1, ya = P(30, y1)
        x2, yb = P(x_right, y2)
        d.rectangle((x1, ya, x2, yb), fill=col)
        cx, cy = P(x_right, y1 + r)
        d.ellipse((cx - r * k, cy - r * k, cx + r * k, cy + r * k), fill=col)

    bowl(75, 18, 76, _mix(GOLD, PURPLE, 0.30))
    bowl(70, 27, 67, _mix(GOLD, PURPLE, 0.60))
    bowl(64, 35, 59, GOLD)
    # trung vị: chấm tròn cách đều
    rr = 1.5 * k
    x = 44.0
    while x <= 101:
        cx, cy = P(x, 47)
        d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=CREAM)
        x += 8
    x1, y1 = P(22, 18)
    x2, y2 = P(40, 102)
    d.rounded_rectangle((x1, y1, x2, y2), radius=int(6 * k), fill=GOLD)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    draw(192, False).save(OUT / "icon-192.png")
    draw(512, False).save(OUT / "icon-512.png")
    draw(512, True).convert("RGB").save(OUT / "icon-maskable.png")
    draw(48, False).save(OUT / "preview-48.png")
    print("wrote icon-192.png, icon-512.png, icon-maskable.png, preview-48.png ->", OUT)


if __name__ == "__main__":
    main()
