"""Accessibility check of the site's pages, in a real browser through nginx.

Runs axe-core (WCAG 2.2 A/AA plus axe's best practices) on every page the user
journeys visit, logged in as each persona, in the light and the dark theme, and
checks that each page reflows at 320px wide (WCAG 1.4.10, no sideways scroll).
Prints what fails and exits 1 when anything does. The Django tests guard the
structure (core.tests.AccessibilityTests); this is the check of what a browser
actually shows: contrast, target sizes, names, landmarks.

    /tmp/uj-venv/bin/python check_a11y.py            # every persona, both themes
    /tmp/uj-venv/bin/python check_a11y.py --quick    # public pages, light theme only

The same venv and seeded logins as the journeys (user-journeys/README.md); the
first run downloads axe-core into .shots/. It changes no data.
"""

import os
import sys
import urllib.request
from collections import defaultdict

from lib import BASE, Journey, sync_playwright

AXE_VERSION = "4.10.2"
AXE_URL = f"https://cdnjs.cloudflare.com/ajax/libs/axe-core/{AXE_VERSION}/axe.min.js"
AXE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".shots", f"axe-{AXE_VERSION}.min.js")

# The seeded ids are the journeys' (dojo 51, events 71/72/76, ninja 9, pathway 1,
# check 352, application 348); adjust them after a reseed.
PERSONAS = {
    None: [
        "/",
        "/dojos/",
        "/dojos/?location=Westerlo&pathway=2",
        "/dojos/51/",
        "/events/",
        "/events/71/",
        "/events/76/",
        "/pathways/1/",
        "/register/",
        "/register/guardian/",
        "/login/",
        "/login/link/",
        "/password-reset/",
        "/contact/",
        "/code-of-conduct/",
    ],
    "guardian-5": [
        "/account/",
        "/account/ninja/9/",
        "/account/edit/",
        "/account/email/",
        "/account/mail/",
        "/account/security/",
        "/account/delete/",
        "/events/71/signup/",
    ],
    "guardian-5-child-1": ["/account/ninja/9/", "/events/72/", "/events/72/signup/"],
    "guardian-11": ["/register/helper/", "/register/dojo/"],
    "owner-51-dojo-westerlo": [
        "/dojos/51/dashboard/",
        "/dojos/51/manage/",
        "/dojos/51/events/",
        "/dojos/51/events/new/",
        "/dojos/51/events/76/",
        "/dojos/51/events/76/attendance/",
        "/dojos/51/manage/team/",
        "/dojos/51/manage/updates/",
        "/dojos/51/manage/members/",
        "/dojos/51/manage/api/",
        "/dojos/51/manage/mail/",
        "/dojos/51/manage/mail/new/",
    ],
    "org-sofie-claes": [
        "/manage/checks/",
        "/manage/checks/352/",
        "/manage/applications/",
        "/manage/applications/348/",
    ],
    "org-priya-nair": [
        "/manage/campaigns/",
        "/manage/campaigns/2/",
        "/manage/segments/",
        "/manage/segments/2/",
        "/manage/journeys/",
        "/manage/templates/",
        "/manage/mail/",
        "/manage/mail/log/",
        "/manage/promotions/",
        "/manage/sponsors/",
        "/manage/awards/",
        "/manage/privacy/",
        "/manage/people/",
        "/manage/security/",
        "/manage/audit-log/",
        "/manage/django-admin/",
    ],
}

AXE_RUN = """async () => {
  const r = await axe.run(document, {runOnly: {type: 'tag', values:
    ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']}, resultTypes: ['violations']});
  return r.violations.map(v => ({id: v.id, impact: v.impact, help: v.help,
    nodes: v.nodes.map(n => ({html: n.html.slice(0, 160), summary: (n.failureSummary || '').slice(0, 200)}))}));
}"""

# Wider than the viewport, and not inside something that scrolls on its own.
REFLOW = """() => {
  const w = document.documentElement.clientWidth;
  const wide = [...document.querySelectorAll('body *')].filter(e => {
    const r = e.getBoundingClientRect();
    if (r.right <= w + 1 || r.width === 0) return false;
    for (let p = e.parentElement; p; p = p.parentElement) {
      if (['auto', 'scroll', 'hidden'].includes(getComputedStyle(p).overflowX)) return false;
    }
    return true;
  });
  return {scroll: document.documentElement.scrollWidth, width: w,
          wide: wide.slice(0, 3).map(e => e.tagName.toLowerCase() + '.' + [...e.classList].join('.'))};
}"""


def ensure_axe():
    if not os.path.exists(AXE):
        os.makedirs(os.path.dirname(AXE), exist_ok=True)
        urllib.request.urlretrieve(AXE_URL, AXE)  # noqa: S310 (a fixed https URL)


def scan(pw, user, paths, theme, viewport=(1280, 860), reflow=False):
    """axe results (or reflow results) per path for one login."""
    j = Journey(f"a11y-{user or 'public'}", pw, viewport=viewport)
    if theme == "dark":
        j.ctx.add_cookies([{"name": "theme", "value": "dark", "url": BASE}])
    j.ctx.add_init_script(path=AXE)  # an init script isn't held to the page's Content-Security-Policy
    if user:
        j.login(user)
    found = {}
    for path in paths:
        page = j.go(path)
        found[path] = page.evaluate(REFLOW) if reflow else page.evaluate(AXE_RUN)
    j.browser.close()
    return found


def main():
    quick = "--quick" in sys.argv
    personas = {None: PERSONAS[None]} if quick else PERSONAS
    ensure_axe()
    problems = 0
    with sync_playwright() as pw:
        for theme in ("light",) if quick else ("light", "dark"):
            rules = defaultdict(list)
            for user, paths in personas.items():
                for path, violations in scan(pw, user, paths, theme).items():
                    for v in violations:
                        rules[(v["id"], v["impact"], v["help"])].append((user or "public", path, v["nodes"]))
            print(f"\n== axe, {theme} theme: {len(rules)} rule(s) failing")
            for (rule, impact, text), pages in rules.items():
                problems += 1
                print(f"  {rule} [{impact}] {text}: {len(pages)} page(s)")
                for who, path, nodes in pages[:5]:
                    print(f"    {who} {path}: {nodes[0]['html'] if nodes else ''}")
        print("\n== reflow at 320px")
        for user, paths in personas.items():
            for path, r in scan(pw, user, paths, "light", viewport=(320, 700), reflow=True).items():
                if r["scroll"] > r["width"] + 1 or r["wide"]:
                    problems += 1
                    print(f"  {user or 'public'} {path}: {r['scroll']}px wide {r['wide']}")
    print("\nNo accessibility problems found." if not problems else f"\n{problems} problem(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
