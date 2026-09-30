"""Which accounts and sessions the load test uses (CAPACITY.md, "Load
tests"), from a `seed_scale` database, as JSON for locustfile.py:

    DB_NAME=test_capacity python manage.py shell -c "exec(open('loadtest/prepare.py').read())" > /tmp/loadtest.json
"""

import json

from accounts.models import Guardianship
from dojos.models import DojoMembership
from events.models import Event, Registration

upcoming = list(Event.objects.filter(status=Event.OPEN).values("id", "dojo_id"))
upcoming_by_dojo = {}
for event in upcoming:
    upcoming_by_dojo.setdefault(event["dojo_id"], []).append(event["id"])

families = {}
for guardian, ninja, dojo in Guardianship.objects.filter(guardian__username__startswith="family").values_list(
    "guardian__username", "ninja_id", "ninja__home_dojo_id"
):
    family = families.setdefault(guardian, {"username": guardian, "children": [], "dojo": dojo})
    family["children"].append(ninja)
for family in families.values():
    family["events"] = upcoming_by_dojo.get(family["dojo"], [])

team = []
for membership in DojoMembership.objects.filter(role=DojoMembership.CHAMPION).select_related("user"):
    past = Event.objects.filter(dojo_id=membership.dojo_id, status=Event.CLOSED).order_by("-start_time").first()
    team.append(
        {
            "username": membership.user.username,
            "dojo": membership.dojo_id,
            "event": past.id,
            "registrations": list(
                Registration.objects.filter(event=past, waiting_list=False).values_list("id", flat=True)
            ),
        }
    )

print(
    json.dumps(
        {
            "families": list(families.values()),
            "team": team,
            "events": [event["id"] for event in upcoming],
            # A handful of sessions everybody wants at once: the rush.
            "rush": [event["id"] for event in upcoming[:5]],
        }
    )
)
