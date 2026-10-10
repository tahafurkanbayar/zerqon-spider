"""`zerqon.ico` dosyasını logo SVG'sinden üretir (yalnızca logo değiştiğinde çalıştırılır).

    .venv/Scripts/python packaging/windows/make_icon.py

SVG, Playwright Chromium ile her boyutta ayrı ayrı (keskin küçük boyutlar için) PNG'ye çizilir,
Pillow ile çok boyutlu ICO dosyasında birleştirilir. Gereksinim: requirements-desktop.txt + Chromium.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
SVG = ROOT / "zerqon" / "web" / "static" / "img" / "logo-mark.svg"
OUT = Path(__file__).resolve().parent / "zerqon.ico"
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def main() -> None:
    svg = SVG.read_text(encoding="utf-8")
    frames: list[Image.Image] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for size in SIZES:
            page = browser.new_page(viewport={"width": size, "height": size})
            html = (
                "<html><body style='margin:0;background:transparent'>"
                f"<div style='width:{size}px;height:{size}px'>{svg.replace('<svg ', f'<svg width=\"{size}\" height=\"{size}\" ', 1)}</div>"
                "</body></html>"
            )
            page.set_content(html)
            png = page.screenshot(omit_background=True, clip={"x": 0, "y": 0, "width": size, "height": size})
            frames.append(Image.open(io.BytesIO(png)).convert("RGBA"))
            page.close()
        browser.close()
    largest = frames[-1]
    largest.save(OUT, format="ICO", sizes=[(s, s) for s in SIZES], append_images=frames[:-1])
    print(f"{OUT} ({OUT.stat().st_size} bayt)")


if __name__ == "__main__":
    main()
