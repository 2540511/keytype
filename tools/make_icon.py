"""生成 KeyType 图标（开发用）。"""

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
SIZE = 512


def load_font(size: int) -> ImageFont.FreeTypeFont:
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidates = [
        windir / "Fonts" / "segoeuib.ttf",
        windir / "Fonts" / "arialbd.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def lerp(a, b, t):
    return int(a + (b - a) * t)


def make_icon() -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # 暖橙色圆角底板，带轻微渐变。
    plate = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    plate_draw = ImageDraw.Draw(plate)
    for y in range(SIZE):
        t = y / (SIZE - 1)
        color = (
            lerp(255, 232, t),
            lerp(191, 147, t),
            lerp(96, 48, t),
            255,
        )
        plate_draw.rectangle((0, y, SIZE, y + 1), fill=color)
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (24, 24, SIZE - 24, SIZE - 24), radius=112, fill=255
    )
    image.paste(plate, (0, 0), mask)

    # 深色按键。
    key_box = (108, 142, 404, 370)
    draw.rounded_rectangle(
        (key_box[0] + 6, key_box[1] + 16, key_box[2] + 10, key_box[3] + 20),
        radius=56,
        fill=(28, 17, 6, 80),
    )
    draw.rounded_rectangle(key_box, radius=54, fill=(27, 17, 7, 255))
    draw.rounded_rectangle(
        (key_box[0] + 14, key_box[1] + 14, key_box[2] - 14, key_box[1] + 60),
        radius=23,
        fill=(48, 32, 14, 255),
    )

    font = load_font(154)
    text = "K"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        (SIZE / 2 - tw / 2 - bbox[0], 256 - th / 2 - bbox[1] + 14),
        text,
        font=font,
        fill=(255, 188, 90, 255),
    )

    # 右侧光标，暗示“正在输入”。
    cursor_x = 420
    draw.rounded_rectangle(
        (cursor_x, 154, cursor_x + 22, 272),
        radius=11,
        fill=(255, 246, 226, 235),
    )

    # 右上角本地状态点。
    draw.ellipse((370, 74, 428, 132), fill=(21, 37, 27, 255))
    draw.ellipse((386, 90, 412, 116), fill=(112, 231, 166, 255))

    return image


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    icon = make_icon()
    icon.save(ASSETS / "icon-512.png")
    icon.resize((256, 256), Image.LANCZOS).save(ASSETS / "icon-256.png")
    icon.save(
        ASSETS / "keytype.ico",
        sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)],
    )
    print("wrote", ASSETS / "keytype.ico")


if __name__ == "__main__":
    main()
