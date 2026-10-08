"""Which accounts and sessions the load test uses (CAPACITY.md, "Load
tests"), from a `seed_scale` database (or a regularly `seed_guardians`-seeded
one — both guardian-username conventions are matched below), as JSON for
locustfile.py:

    DB_NAME=test_capacity python manage.py shell -c "exec(open('loadtest/prepare.py').read())" > /tmp/loadtest.json
"""

import json

from django.db.models import Q

from accounts.models import Guardianship
from dojos.models import DojoMembership
from events.models import Event, Registration

upcoming = list(Event.objects.filter(status=Event.OPEN).values("id", "dojo_id"))
upcoming_by_dojo = {}
for event in upcoming:
    upcoming_by_dojo.setdefault(event["dojo_id"], []).append(event["id"])

# seed_scale names guardians "family0", "family1", ...; seed_guardians names
# them "guardian-0", "guardian-1", ... — match either.
families = {}
for guardian, ninja, dojo in Guardianship.objects.filter(
    Q(guardian__username__startswith="family") | Q(guardian__username__startswith="guardian-")
).values_list("guardian__username", "ninja_id", "ninja__home_dojo_id"):
    family = families.setdefault(guardian, {"username": guardian, "children": [], "dojo": dojo})
    family["children"].append(ninja)
for family in families.values():
    family["events"] = upcoming_by_dojo.get(family["dojo"], [])

team = []
for membership in DojoMembership.objects.filter(role=DojoMembership.CHAMPION).select_related("user"):
    past = Event.objects.filter(dojo_id=membership.dojo_id, status=Event.CLOSED).order_by("-start_time").first()
    if not past:
        # A champion whose dojo has no closed event yet (a draft/dormant/
        # archived dojo, or a lightly seeded database): nothing to take
        # attendance on, so this dojo sits out the team-attendance traffic.
        continue
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
