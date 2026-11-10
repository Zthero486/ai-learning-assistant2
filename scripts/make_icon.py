# -*- coding: utf-8 -*-
"""重新生成应用图标：白字改为「AI」，其余风格（红蓝渐变圆角方块）与原图一致。

产出：
  frontend/public/icon-512.png / icon-192.png / apple-touch-icon.png / favicon-32.png
  assets/app.ico（PyInstaller --icon 用，含 16~256 多尺寸）
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "frontend" / "public"
ASSETS = ROOT / "assets"

# 从旧图标采样渐变端色，保持品牌色不变
old = Image.open(PUBLIC / "icon-512.png").convert("RGBA")
top = old.getpixel((256, 6))[:3]
bottom = old.getpixel((256, 506))[:3]
print("渐变采样:", top, "->", bottom)

FONT = r"C:\Windows\Fonts\arialbd.ttf"


def make(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    # 垂直渐变
    px = img.load()
    for y in range(size):
        t = y / (size - 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        for x in range(size):
            px[x, y] = (r, g, b, 255)
    # 圆角裁切（圆角比例与原图一致：约 100/512）
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=int(size * 0.195), fill=255
    )
    img.putalpha(mask)
    # 「AI」白字居中
    d = ImageDraw.Draw(img)
    fsize = int(size * 0.44)
    font = ImageFont.truetype(FONT, fsize)
    text = "AI"
    l, t_, r_, b_ = d.textbbox((0, 0), text, font=font)
    w, h = r_ - l, b_ - t_
    d.text(((size - w) / 2 - l, (size - h) / 2 - t_), text, font=font, fill=(255, 255, 255, 255))
    return img


for name, s in [
    ("icon-512.png", 512),
    ("icon-192.png", 192),
    ("apple-touch-icon.png", 180),
    ("favicon-32.png", 32),
]:
    make(s).save(PUBLIC / name)
    print("written", PUBLIC / name)

# 多尺寸 ico
ASSETS.mkdir(exist_ok=True)
base = make(256)
base.save(ASSETS / "app.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("written", ASSETS / "app.ico")
