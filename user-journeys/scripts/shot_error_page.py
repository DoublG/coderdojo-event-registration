"""The proxy's own "busy" page (.devcontainer/nginx/errors/busy.html, CAPACITY.md
"Capping requests per web worker") as one image for the documents: the desktop in
light mode next to a phone in dark mode. Opens the file itself, so no site needs to
run; the site's fonts load from /static/ only behind the proxy, so this shows the
fallback font. Same venv as the journeys (playwright, pillow; README.md).

    python user-journeys/scripts/shot_error_page.py
"""

import io
import os

from PIL import Image
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
PAGE = os.path.join(REPO, ".devcontainer", "nginx", "errors", "busy.html")
OUT = os.path.join(REPO, "user-journeys", "images", "proxy-busy-page.png")
GAP, MARGIN, BACKGROUND = 32, 24, (252, 252, 251)


def shot(browser, width, height, scheme):
    page = browser.new_page(viewport={"width": width, "height": height}, color_scheme=scheme, device_scale_factor=2)
    page.goto(f"file://{PAGE}")
    image = Image.open(io.BytesIO(page.screenshot(full_page=True)))
    page.close()
    return image


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome")
        desktop = shot(browser, 900, 900, "light")
        phone = shot(browser, 390, 844, "dark")
        browser.close()
    # The phone at the desktop's height, side by side on the documents' background.
    phone = phone.resize((round(phone.width * desktop.height / phone.height), desktop.height), Image.LANCZOS)
    margin, gap = MARGIN * 2, GAP * 2  # at the 2x scale of the screenshots
    canvas = Image.new(
        "RGB", (desktop.width + gap + phone.width + 2 * margin, desktop.height + 2 * margin), BACKGROUND
    )
    canvas.paste(desktop, (margin, margin))
    canvas.paste(phone, (margin + desktop.width + gap, margin))
    canvas = canvas.resize((canvas.width // 2, canvas.height // 2), Image.LANCZOS)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    canvas.save(OUT, optimize=True)
    print(OUT)


if __name__ == "__main__":
    main()
