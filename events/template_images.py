"""Ready-made session banner images shipped with the app — under
events/static/events/template_images/ so they're reachable via {% static %}
as well as plain filesystem access. Shared by the demo-data seeder
(seed_events.py, seed_participant_history.py) and the dojo owner's own
"choose from templates" banner option on the event-create form
(events.forms.EventForm) — a single source of truth so the two never
drift out of sync on which files/names exist.
"""

from pathlib import Path

TEMPLATE_IMAGES_DIR = Path(__file__).resolve().parent / "static" / "events" / "template_images"

# (filename, label) — filename must exist under TEMPLATE_IMAGES_DIR.
TEMPLATE_IMAGES = [
    ("coding-saturday.svg", "Coding Saturday"),
    ("open-lab.svg", "Open Lab"),
    ("scratch-games.svg", "Scratch & Games"),
    ("build-code.svg", "Build & Code"),
    ("ninja-session.svg", "Ninja Session"),
    ("code-club.svg", "Code Club"),
    ("make-something.svg", "Make Something Session"),
    ("project-time.svg", "Project Time"),
    ("beginners-workshop.svg", "Beginner's Workshop"),
    ("game-jam.svg", "Game Jam Session"),
]
