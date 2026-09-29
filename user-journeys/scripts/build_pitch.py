"""The pitch decks as PDFs: pitch-deck/<lang>/ (a copy of the Slides artifacts' files) → <lang>/pitch-deck.pdf.

The decks themselves live on claude.ai (links in user-journeys/README.md); this renders the same slide
files to 1920x1080 pages with Chrome, so a copy sits next to the user journeys. Screenshots come
from .shots/<lang>/ (made by the j_*.py scripts), cropped the way they were for the decks, and the
Slides app's icons are drawn as simple line icons. Run: python build_pitch.py en|nl
"""

import base64
import io
import json
import os
import re
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LANG = sys.argv[1] if len(sys.argv) > 1 else "en"
DECK = os.path.join(ROOT, "pitch-deck", LANG)
SHOTS = os.path.join(ROOT, ".shots", LANG)
OUT = os.path.join(ROOT, LANG, "pitch-deck.pdf" if LANG == "en" else "pitchdeck.pdf")

# Each screenshot's asset id in the deck → the journey screenshot it was cropped from.
IMAGES = {
    "en": {
        "73efff6ddd32673925fb242487c13de6": "parent/01-home",
        "c339e386449fe8b5f995550569db0e6e": "parent/07-account",
        "ea6d15d31619dc36eefb380fb96df817": "ninja/02-me",
        "35624d23345072cc7c5da05b7f7adbc3": "volunteer/02-apply-mentor",
        "5fdb55e406618de44afca53892307416": "volunteer/10-attendance",
        "bd05ec3f4b068a2f57a878df4bd4bc86": "champion/04-new-event",
        "57be58b44279969f953d13df818bb170": "reviewer/02-checks",
        "d1fbce1a3d89297ea652afe161cabdc1": "organisation/04-segment",
    },
    "nl": {
        "030a3bfbf5c06a742f104f058ddf0d75": "parent/01-home",
        "a60d18682501229e05153d575432b17c": "parent/07-account",
        "b3a86da0bc9216e27aeba57cb23335cb": "ninja/02-me",
        "ff3020d59a424c070256eb052a729ffb": "volunteer/02-apply-mentor",
        "dd0b7a465872a0edc5c9c1497061a7c2": "volunteer/10-attendance",
        "8edcd90f370ae0d2e68b9968ebc7ed8d": "champion/04-new-event",
        "de97d5be5e386ce4e6413d94c3344da5": "reviewer/02-checks",
        "319ea5fcfd162f1f3dc1aa1e75e630d2": "organisation/04-segment",
    },
}

# Line icons (24x24, stroke = currentColor) for the <x-icon> names the slides use.
ICONS = {
    "Home": '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M10 21v-6h4v6"/>',
    "Users": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6"/>'
    '<circle cx="17" cy="9" r="2.8"/><path d="M16.5 14.2c2.8.2 5 2.3 5 5.3"/>',
    "Globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3c2.8 2.6 2.8 15.4 0 18"/>'
    '<path d="M12 3c-2.8 2.6-2.8 15.4 0 18"/>',
    "Star": '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>',
    "Key": '<circle cx="8" cy="15" r="4.5"/><path d="M11.2 11.8 20 3"/><path d="M16.5 6.5l2.5 2.5"/>'
    '<path d="M14 9l2 2"/>',
    "Verified": '<path d="M12 2.5l2.4 1.8 3-.2.9 2.9 2.5 1.7-1 2.8 1 2.8-2.5 1.7-.9 2.9-3-.2L12 21.5'
    'l-2.4-1.8-3 .2-.9-2.9-2.5-1.7 1-2.8-1-2.8 2.5-1.7.9-2.9 3 .2z"/><path d="M8.5 12l2.4 2.4 4.6-4.8"/>',
    "Lock": '<rect x="4.5" y="10.5" width="15" height="10.5" rx="2"/><path d="M8 10.5V7a4 4 0 0 1 8 0v3.5"/>',
    "Trust": '<path d="M12 2.5 20 6v6c0 4.6-3.4 8.3-8 9.5-4.6-1.2-8-4.9-8-9.5V6z"/><path d="M8.5 12l2.4 2.4 4.6-4.8"/>',
    "Book": '<path d="M4 4.5A1.5 1.5 0 0 1 5.5 3H20v15H5.5A1.5 1.5 0 0 0 4 19.5z"/><path d="M4 19.5A1.5 1.5 0 0 0 5.5 21H20"/>',
}

CSS = """
@page { size: 1920px 1080px; margin: 0; }
html, body { margin: 0; padding: 0; background: #ffffff; }
section { width: 1920px; height: 1080px; box-sizing: border-box; position: relative; overflow: hidden;
          break-after: page; page-break-after: always; }
section:last-of-type { break-after: auto; page-break-after: auto; }
h1, h2, h3, p, ul, ol { margin: 0; }
ul, ol { padding-left: 1.2em; }
aside { display: none; }
table { border-collapse: collapse; width: 100%; }
th, td { padding: 0.35em 0.6em; border-bottom: 1px solid #e2e6eb; vertical-align: top; }
th { font-weight: 700; }
.icon { display: block; flex: none; }
"""


def screenshot(path):
    im = Image.open(os.path.join(SHOTS, path + ".png")).convert("RGB")
    im = im.crop((0, 0, im.width, min(im.height, int(im.width * 10 / 16))))
    im = im.resize((1440, round(im.height * 1440 / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def icon(match):
    name, style = match.group(1), match.group(2)
    return (
        f'<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round" style="{style}">{ICONS[name]}</svg>'
    )


def main():
    deck = json.load(open(os.path.join(DECK, "deck.json")))
    images = {blob: screenshot(path) for blob, path in IMAGES[LANG].items()}
    slides = []
    for slide_id in deck["order"]:
        html = open(os.path.join(DECK, "slides", f"{slide_id}.html")).read()
        html = re.sub(r"/_blob/([0-9a-f]{32})", lambda m: images[m.group(1)], html)
        html = re.sub(r'<x-icon name="(\w+)" style="([^"]*)"></x-icon>', icon, html)
        slides.append(html)
    fonts = "".join(f'<link rel="stylesheet" href="{face["href"]}">' for face in deck["faces"].values())
    doc = (
        f"<!doctype html><html lang='{LANG}'><head><meta charset='utf-8'><title>{deck['title']}</title>"
        f"{fonts}<style>{CSS}</style></head><body>{''.join(slides)}</body></html>"
    )
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.set_content(doc, wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        page.pdf(path=OUT, width="1920px", height="1080px", print_background=True, prefer_css_page_size=True)
        browser.close()
    print(OUT)


if __name__ == "__main__":
    main()
