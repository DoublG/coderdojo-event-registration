import csv
import json
import os
import ssl
import subprocess
import time
import urllib.parse
import urllib.request

import pyotp
from playwright.sync_api import sync_playwright  # noqa: F401 (the journey scripts import it from here)

BASE = "https://coolregistration.localhost"
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
CREDS = {r["username"]: r for r in csv.DictReader(open(os.path.join(REPO, "seed_credentials.csv")))}
HIDE = "#djDebug, #djDebugRoot { display: none !important; }"

LANG = os.environ.get("JLANG", "en")
SHOTS = os.path.join(os.path.dirname(HERE), ".shots", LANG)


class Journey:
    def __init__(self, persona, pw, viewport=(1280, 860), mobile=False):
        self.persona = persona
        self.dir = os.path.join(SHOTS, persona)
        os.makedirs(self.dir, exist_ok=True)
        self.steps = []
        self.browser = pw.chromium.launch(channel="chrome", headless=True)
        loc, acc = {
            "nl": ("nl-BE", "nl-BE,nl;q=0.9"),
            "fr": ("fr-BE", "fr-BE,fr;q=0.9"),
        }.get(LANG, ("en-US", "en-US,en;q=0.9"))
        kw = dict(
            ignore_https_errors=True,
            locale=loc,
            viewport={"width": viewport[0], "height": viewport[1]},
            device_scale_factor=1.5,
            extra_http_headers={"Accept-Language": acc},
            color_scheme="light",
        )
        self.ctx = self.browser.new_context(**kw)
        self.ctx.add_init_script(
            "document.addEventListener('DOMContentLoaded',()=>{const s=document.createElement('style');"
            f"s.textContent={json.dumps(HIDE)};document.head.appendChild(s);}});"
        )
        self._lang_cookie()
        self.page = self.ctx.new_page()
        self.page.set_default_timeout(15000)

    def go(self, path):
        self.page.goto(BASE + path, wait_until="networkidle")
        return self.page

    def shot(self, key, title, text, max_h=1500, full=True, selector=None):
        p = self.page
        p.wait_for_timeout(400)
        # An htmx endpoint opened on its own returns a fragment: no stylesheet, no page shell, so the
        # screenshot is unstyled. Open the whole page and click to the part instead.
        # (The site's own stylesheet, from /static/: the debug toolbar and our init script add <style>
        # to fragments too. Mailpit's pages aren't the site's.)
        site_css = "!!document.querySelector('link[rel=stylesheet][href*=\"/static/\"]')"
        if "/mails/" not in p.url and not p.evaluate(site_css):
            raise RuntimeError(
                f"{self.persona}/{key}: {p.url} has no stylesheet: an htmx fragment, not a page. "
                "Screenshot the page that loads it (and click to open that part) instead."
            )
        path = os.path.join(self.dir, f"{len(self.steps) + 1:02d}-{key}.png")
        if selector:
            p.locator(selector).first.screenshot(path=path)
        else:
            h = p.evaluate("document.documentElement.scrollHeight") if full else p.viewport_size["height"]
            h = min(h, max_h)
            p.screenshot(
                path=path, clip={"x": 0, "y": 0, "width": p.viewport_size["width"], "height": h}, full_page=True
            )
        self.steps.append({"key": key, "title": title, "text": text, "image": path, "url": p.url.replace(BASE, "")})
        print("shot", key, p.url)

    def login(self, username, shoot_login=None, shoot_token=None):
        c = CREDS[username]
        p = self.go("/login/")
        p.fill("#id_auth-username", username)
        p.fill("#id_auth-password", c["password"])
        if shoot_login:
            self.shot(*shoot_login, full=False)
        p.click("#login-form button[type=submit]")
        p.wait_for_load_state("networkidle")
        if c["totp_secret"] and p.locator("input[name='token-otp_token']").count():
            p.fill("input[name='token-otp_token']", pyotp.TOTP(c["totp_secret"]).now())
            if shoot_token:
                self.shot(*shoot_token, full=False)
            p.locator("input[name='token-otp_token']").press("Enter")
            p.wait_for_load_state("networkidle")
        print("logged in", username, p.url)

    def _lang_cookie(self):
        code = {"nl": "nl-be", "fr": "fr-be"}.get(LANG, "en-us")
        self.ctx.add_cookies([{"name": "django_language", "value": code, "url": BASE}])

    def logout(self):
        self.ctx.clear_cookies()
        self._lang_cookie()

    def save(self, meta):
        meta = dict(meta, steps=self.steps)
        json.dump(meta, open(os.path.join(self.dir, "journey.json"), "w"), indent=1)
        self.browser.close()


_ssl = ssl.create_default_context()
_ssl.check_hostname = False
_ssl.verify_mode = ssl.CERT_NONE


def mail_ids(to):
    u = BASE + "/mails/api/v1/search?query=" + urllib.parse.quote(f"to:{to}")
    return [m["ID"] for m in json.load(urllib.request.urlopen(u, context=_ssl))["messages"]]


def django(code):
    return subprocess.run(
        [
            "docker",
            "exec",
            "-w",
            "/workspace",
            "coolregistration-dev-workspace",
            "python",
            "manage.py",
            "shell",
            "-c",
            code,
        ],
        capture_output=True,
        text=True,
    ).stdout


def mail_shot(j, to, before, key, title, text, wait=90):
    t = time.time()
    while time.time() - t < wait:
        new = [i for i in mail_ids(to) if i not in before]
        if new:
            break
        time.sleep(3)
    else:
        print("NO MAIL for", to)
        return
    old = j.page
    j.page = j.ctx.new_page()
    j.page.set_viewport_size({"width": 1280, "height": 760})
    j.page.goto(BASE + "/mails/view/" + new[0], wait_until="networkidle")
    j.shot(key, title, text, full=False)
    j.page.close()
    j.page = old
