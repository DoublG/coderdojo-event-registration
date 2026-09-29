"""Ready-made profile pictures shipped with the app — under
accounts/static/accounts/ so they're reachable via {% static %} as well as
plain filesystem access. Same idea as events/template_images.py and
dojos/template_icons.py: one source of truth for which files/names exist,
used by the demo-data seeders and the ninja avatar picker on the account
pages, and linked from the shared image library (core.image_library).
"""

from pathlib import Path

from django.utils.translation import gettext_lazy as _

STATIC_DIR = Path(__file__).resolve().parent / "static" / "accounts"

# Adults: team-page profiles (User.photo) and the organisation's team listing.
TEMPLATE_AVATARS_DIR = STATIC_DIR / "template_avatars"

# (filename, label) — filename must exist under TEMPLATE_AVATARS_DIR.
TEMPLATE_AVATARS = [(f"avatar-{n:02d}.svg", f"Avatar {n}") for n in range(1, 11)]

# Ninjas (the kids) get a more playful set — aliens, robots, animals.
TEMPLATE_KID_AVATARS_DIR = STATIC_DIR / "template_kid_avatars"

# (filename, label) — filename must exist under TEMPLATE_KID_AVATARS_DIR. The
# labels are shown to families and to the child's own login, so translated.
TEMPLATE_KID_AVATARS = [
    ("alien-01-green.svg", _("Green Alien")),
    ("alien-02-purple.svg", _("Purple Alien")),
    ("alien-03-blue.svg", _("Blue Alien")),
    ("animal-01-fox.svg", _("Fox")),
    ("animal-02-cat.svg", _("Cat")),
    ("animal-03-owl.svg", _("Owl")),
    ("animal-04-panda.svg", _("Panda")),
    ("robot-01-cyclops.svg", _("Cyclops Robot")),
    ("robot-02-square.svg", _("Square Robot")),
    ("robot-03-headphones.svg", _("Headphones Robot")),
    # Pixel robots after the ones on coderdojobelgium.be.
    ("robot-04-antennae.svg", _("Blue Antenna Robot")),
    ("robot-05-forks.svg", _("Teal Fork Robot")),
    ("robot-06-box.svg", _("Yellow Box Robot")),
    ("robot-07-dome.svg", _("Red Dome Robot")),
    ("robot-08-goggles.svg", _("Green Goggle Robot")),
    ("robot-09-earmuffs.svg", _("Red Earmuff Robot")),
    ("robot-10-ghost.svg", _("Blue Ghost Robot")),
    ("robot-11-lights.svg", _("Teal Lights Robot")),
]
