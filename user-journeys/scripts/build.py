import base64
import html
import io
import json
import os
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

LANG = sys.argv[1] if len(sys.argv) > 1 else "en"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, LANG)
os.makedirs(OUT, exist_ok=True)
SHOTS = os.path.join(ROOT, ".shots", LANG)
UI_EN = {
    "brand": "CoderDojo Belgium · user journey",
    "who": "Screenshots taken on the development site (seeded demo data) as <b>{who}</b>, 29 September 2026.",
    "journey": "The journey",
    "steps": "Steps in this document",
    "foot": "coolregistration.localhost · generated from the running application",
    "step": "Step",
    "continued": "(continued)",
    "footer": "CoderDojo Belgium · {title} journey",
}
NAMES = {
    "en": {k: f"{k}-journey" for k in ["parent", "ninja", "volunteer", "champion", "reviewer", "organisation"]},
    "nl": {
        "parent": "ouder",
        "ninja": "ninja",
        "volunteer": "vrijwilliger",
        "champion": "champion",
        "reviewer": "beoordelaar",
        "organisation": "organisatie",
    },
}
INTRO = {
    "parent": (
        "Parent",
        "A parent or guardian finds a dojo, creates a family account and signs their children up for sessions. Parents don't need approval or a background check: they only ever manage their own children.",
        [
            "Discover dojos and sessions without an account",
            "Create a family account with the children in one go",
            "Follow each child's belts, badges and history",
            "Sign up for a session, and get the confirmation mail",
            "Manage mail, sign-in security and privacy",
        ],
    ),
    "ninja": (
        "Ninja",
        "A child aged 7–17 who comes to a dojo. Most ninjas never log in; their parent can give them a login of their own, so they can follow their progress and sign themselves up.",
        [
            "Log in with the login a parent set up",
            "See belts, badges and session history",
            "Explore learning pathways",
            "Sign themselves up for a session",
            "Manage their own sign-in security",
        ],
    ),
    "volunteer": (
        "Volunteer (mentor)",
        "An adult who wants to help at a dojo. Becoming a mentor is a one-time, account-level approval: an application plus a valid Belgian background check. After that they can join any dojo's team and help run its sessions.",
        [
            "Apply to be a mentor (or to start a dojo)",
            "Upload the background check when asked",
            "Wait for the reviewers' decision",
            "Work in the dojo's management area: sessions and attendance",
            "Award belts and badges, manage the team, join other dojos",
        ],
    ),
    "champion": (
        "Champion",
        "The person who runs a dojo. The champion has every mentor capability plus the dojo's lifecycle, the children's health notes, mail to the dojo's families and the dojo's API clients.",
        [
            "Watch the dashboard and next session",
            "Keep the dojo's public profile up to date",
            "Plan and publish sessions, handle the waiting list",
            "Take attendance, manage the team and members",
            "Post updates, mail families, connect apps",
        ],
    ),
    "reviewer": (
        "Background-check reviewer",
        "An organisation role that only reviews background checks and decides volunteer applications, in the Volunteers group of the organisation dashboard.",
        [
            "Sign in with two-step login",
            "Work through the queue of background checks",
            "Validate or reject a document (which is then deleted)",
            "Approve or decline mentor and champion applications",
        ],
    ),
    "organisation": (
        "Organisation admin",
        "CoderDojo Belgium's own staff and board. The organisation dashboard covers communication, the public site, awards, privacy requests, people and security; the Django admin is only for technical fixes, on request.",
        [
            "Mail campaigns, segments, journeys and templates",
            "Watch the mail queue",
            "Promotions, sponsors and awards",
            "Privacy requests, people and roles, sign-in policy",
            "Audit log and time-boxed Django admin access",
        ],
    ),
}
ORDER = ["parent", "ninja", "volunteer", "champion", "reviewer", "organisation"]
CSS = """
@page { size: A4; margin: 14mm 14mm 16mm; }
* { box-sizing: border-box; }
body { font-family: 'Nunito', 'Segoe UI', Arial, sans-serif; color: #1f2937; margin: 0; font-size: 11pt; }
.cover { height: 262mm; display: flex; flex-direction: column; page-break-after: always; }
.brand { color: #c94a23; font-weight: 800; letter-spacing: .04em; text-transform: uppercase; font-size: 10pt; }
h1 { font-size: 34pt; margin: 8mm 0 3mm; line-height: 1.05; }
.sub { font-size: 13pt; color: #4b5563; max-width: 150mm; line-height: 1.45; }
.who { margin-top: 5mm; font-size: 9.5pt; color: #6b7280; }
.box { margin-top: 9mm; background: #f3f4f6; border-radius: 4mm; padding: 6mm 8mm; }
.box h2 { font-size: 12pt; margin: 0 0 3mm; }
.box ul { margin: 0; padding-left: 5mm; line-height: 1.6; }
ol.toc { columns: 2; column-gap: 10mm; padding-left: 6mm; line-height: 1.7; font-size: 10pt; margin: 0; }
.foot { margin-top: auto; font-size: 8.5pt; color: #9ca3af; }
.step { page-break-before: always; }
.step:first-of-type { page-break-before: auto; }
.num { display: inline-block; background: #c94a23; color: white; border-radius: 99px; padding: 1mm 3.2mm; font-weight: 800; font-size: 10pt; }
.step h2 { font-size: 18pt; margin: 3mm 0 2mm; }
.step p { margin: 0 0 2mm; line-height: 1.5; max-width: 175mm; }
.url { font-family: monospace; font-size: 8.5pt; color: #6b7280; margin-bottom: 3mm; }
.shot { text-align: center; }
.cont { color:#6b7280; font-weight:700; margin-left:2mm; }
.shot img.tall { max-height: 240mm; }
.shot img { max-width: 100%; max-height: 190mm; border: 0.3mm solid #d1d5db; border-radius: 2mm; box-shadow: 0 1mm 3mm rgba(0,0,0,.08); }
"""


def build(key, page):
    d = json.load(open(f"{SHOTS}/{key}/journey.json"))
    ui = UI_EN
    title, sub, bullets = INTRO[key]
    who = d["who"]
    if LANG == "nl":
        import nl

        ui = nl.UI
        title, sub, bullets = nl.INTRO[key]
        who = nl.WHO[key]
        for s in d["steps"]:
            s["title"], s["text"] = nl.STEPS[key][s["key"]]
    for s in d["steps"]:
        s["image"] = os.path.join(SHOTS, key, os.path.basename(s["image"]))
    toc = "".join(f"<li>{html.escape(s['title'])}</li>" for s in d["steps"])
    parts = [
        f"<div class='cover'><div class='brand'>{ui['brand']}</div><h1>{title}</h1><div class='sub'>{html.escape(sub)}</div>",
        "<div class='who'>" + ui["who"].format(who=html.escape(who)) + "</div>",
        f"<div class='box'><h2>{ui['journey']}</h2><ul>"
        + "".join(f"<li>{html.escape(b)}</li>" for b in bullets)
        + "</ul></div>",
        f"<div class='box'><h2>{ui['steps']}</h2><ol class='toc'>{toc}</ol></div>",
        f"<div class='foot'>{ui['foot']}</div></div>",
    ]
    for i, s in enumerate(d["steps"], 1):
        im = Image.open(s["image"]).convert("RGB")
        if im.width > 1400:
            im = im.resize((1400, round(im.height * 1400 / im.width)), Image.LANCZOS)
        first_h = int(im.width * 1.02)
        rest_h = int(im.width * 1.3)
        chunks, y = [], 0
        while y < im.height and len(chunks) < 3:
            h = first_h if not chunks else rest_h
            if im.height - (y + h) < im.width * 0.12:
                h = im.height - y  # avoid a sliver
            chunks.append(im.crop((0, y, im.width, min(im.height, y + h))))
            y += h
        imgs = []
        for c in chunks:
            b = io.BytesIO()
            c.save(b, "JPEG", quality=78)
            imgs.append(base64.b64encode(b.getvalue()).decode())
        head = f"<span class='num'>{ui['step']} {i}</span><h2>{html.escape(s['title'])}</h2><p>{html.escape(s['text'])}</p><div class='url'>{html.escape(s['url'])}</div>"
        parts.append(
            f"<section class='step'>{head}<div class='shot'><img src='data:image/jpeg;base64,{imgs[0]}'></div></section>"
        )
        for c in imgs[1:]:
            parts.append(
                f"<section class='step'><span class='num'>{ui['step']} {i}</span> <span class='cont'>{html.escape(s['title'])} {ui['continued']}</span><div class='shot' style='margin-top:4mm'><img class='tall' src='data:image/jpeg;base64,{c}'></div></section>"
            )
    doc = f"<!doctype html><html lang='{LANG}'><head><meta charset='utf-8'><title>{title}</title><style>{CSS}</style></head><body>{''.join(parts)}</body></html>"
    page.set_content(doc, wait_until="load")
    n = ORDER.index(key) + 1
    out = f"{OUT}/{n}-{NAMES[LANG][key]}.pdf"
    page.pdf(
        path=out,
        format="A4",
        print_background=True,
        display_header_footer=True,
        header_template="<span></span>",
        footer_template=f"<div style='font-size:7pt;color:#9ca3af;width:100%;padding:0 14mm;display:flex;justify-content:space-between'><span>{ui['footer'].format(title=title.lower() if LANG == 'nl' else title)}</span><span><span class='pageNumber'></span> / <span class='totalPages'></span></span></div>",
        margin={"top": "14mm", "bottom": "16mm", "left": "14mm", "right": "14mm"},
    )
    print(out)


with sync_playwright() as pw:
    b = pw.chromium.launch(channel="chrome")
    page = b.new_page()
    for k in ORDER:
        build(k, page)
    b.close()
