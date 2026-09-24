"""Ready-made profile pictures shipped with the app — under
accounts/static/accounts/ so they're reachable via {% static %} as well as
plain filesystem access. Same idea as events/template_images.py and
dojos/template_icons.py: one source of truth for which files/names exist,
used by the demo-data seeders and the ninja avatar picker on the account
pages, and linked from the shared image library (core.image_library).
"""

from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent / "static" / "accounts"

# Adults: team-page profiles (User.photo) and the organisation's team listing.
TEMPLATE_AVATARS_DIR = STATIC_DIR / "template_avatars"

# (filename, label) — filename must exist under TEMPLATE_AVATARS_DIR.
TEMPLATE_AVATARS = [(f"avatar-{n:02d}.svg", f"Avatar {n}") for n in range(1, 11)]

# Ninjas (the kids) get a more playful set — aliens, robots, animals.
TEMPLATE_KID_AVATARS_DIR = STATIC_DIR / "template_kid_avatars"

# (filename, label) — filename must exist under TEMPLATE_KID_AVATARS_DIR.
TEMPLATE_KID_AVATARS = [
    ("alien-01-green.svg", "Green Alien"),
    ("alien-02-purple.svg", "Purple Alien"),
    ("alien-03-blue.svg", "Blue Alien"),
    ("animal-01-fox.svg", "Fox"),
    ("animal-02-cat.svg", "Cat"),
    ("animal-03-owl.svg", "Owl"),
    ("animal-04-panda.svg", "Panda"),
    ("robot-01-cyclops.svg", "Cyclops Robot"),
    ("robot-02-square.svg", "Square Robot"),
    ("robot-03-headphones.svg", "Headphones Robot"),
]
