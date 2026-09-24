import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import User
from applications.models import Application, BackgroundCheckHistory
from dojos.models import Dojo

# (background check status on the account, application status) for a few
# demo parents who applied to mentor — one per stage of the review queue.
STAGES = [
    (User.CHECK_NOT_REQUESTED, Application.PENDING),
    (User.CHECK_REQUESTED, Application.PENDING),
    (User.CHECK_SUBMITTED, Application.PENDING),
    (User.CHECK_REJECTED, Application.REJECTED),
]


class Command(BaseCommand):
    help = (
        "Seed a few mentor applications from demo parents, one at each stage of the "
        "review flow (check not requested / requested / submitted-awaiting-review / "
        "rejected), so the admin's Applications and Background checks lists have "
        "something to work through. Needs seed_guardians to have run first."
    )

    def handle(self, *args, **options):
        rng = random.Random(11)
        parents = list(
            User.objects.filter(username__startswith="guardian-", account_type=User.ADULT).order_by("id")[:len(STAGES)]
        )
        dojos = list(Dojo.objects.public().order_by("id")[:10])
        created = 0
        now = timezone.now()

        for parent, (check_status, application_status) in zip(parents, STAGES):
            if parent.applications.exists():
                continue
            Application.objects.create(
                account=parent, kind=Application.MENTOR, status=application_status,
                dojo=rng.choice(dojos) if dojos else None, mentor_role=Application.VOLUNTEER_MENTOR,
                message="I'd love to help out with Scratch sessions on Saturdays.",
                background_check_consent=True,
                decided_at=now if application_status != Application.PENDING else None,
            )
            parent.background_check_status = check_status
            if check_status != User.CHECK_NOT_REQUESTED:
                parent.background_check_requested_at = now - timedelta(days=10)
            if check_status in (User.CHECK_SUBMITTED, User.CHECK_REJECTED):
                parent.background_check_submitted_at = now - timedelta(days=3)
            if check_status == User.CHECK_REJECTED:
                parent.background_check_reviewed_at = now - timedelta(days=1)
                BackgroundCheckHistory.objects.create(
                    account=parent, decision=BackgroundCheckHistory.REJECTED, reviewed_at=parent.background_check_reviewed_at,
                    requested_at=parent.background_check_requested_at, submitted_at=parent.background_check_submitted_at,
                    note="Seed data: wrong document (model 1 instead of model 2).",
                )
            parent.save()
            created += 1

        self.stdout.write(self.style.SUCCESS(f"Done. created={created} applications."))
