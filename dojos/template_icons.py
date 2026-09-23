"""Ready-made round icons shipped with the app — under
dojos/static/dojos/template_icons/ so they're reachable via {% static %} as
well as plain filesystem access. Shared by the demo-data seeder
(seed_mentors.py's assign_dojo_icon) and the dojo owner's own "choose from
templates" icon option on the profile-settings form
(dojos.forms.DojoProfileForm) — a single source of truth so the two never
drift out of sync on which files exist.
"""

from pathlib import Path

TEMPLATE_ICONS_DIR = Path(__file__).resolve().parent / "static" / "dojos" / "template_icons"

# (filename, label) — filename must exist under TEMPLATE_ICONS_DIR.
TEMPLATE_ICONS = [
    ("icon-01-code.svg", "Code"),
    ("icon-02-robot.svg", "Robot"),
    ("icon-03-controller.svg", "Controller"),
    ("icon-04-circuit.svg", "Circuit"),
    ("icon-05-rocket.svg", "Rocket"),
    ("icon-06-lightbulb.svg", "Lightbulb"),
    ("icon-07-gear.svg", "Gear"),
    ("icon-08-chip.svg", "Chip"),
]
