from django.contrib.gis.db import models


class Event(models.Model):
    name = models.CharField(max_length=200)
    dojo = models.ForeignKey("dojos.Dojo", on_delete=models.CASCADE)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    places = models.IntegerField()

    location = models.PointField(srid=4326, null=True, blank=True, spatial_index=False)
    venue_name = models.CharField(max_length=200, blank=True, default="", help_text='e.g. "Ghent Public Library"')

    description = models.TextField(blank=True, default="")
    what_to_bring = models.TextField(blank=True, default="")
    min_age = models.PositiveSmallIntegerField(null=True, blank=True)
    max_age = models.PositiveSmallIntegerField(null=True, blank=True)
    mentor = models.ForeignKey("dojos.Mentor", on_delete=models.SET_NULL, null=True, blank=True, related_name="events")

    participants = models.ManyToManyField("accounts.Participant", through="Registration")

    def __str__(self):
        return f"{self.name} ({self.dojo})"

    @property
    def places_left(self):
        confirmed = self.registration_set.filter(waiting_list=False).count()
        return self.places - confirmed


class Registration(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    participant = models.ForeignKey("accounts.Participant", on_delete=models.CASCADE)
    waiting_list = models.BooleanField()
    position = models.IntegerField()

    # Tri-state: None = not yet marked, True = present, False = absent.
    attended = models.BooleanField(null=True, blank=True)
    pathway = models.ForeignKey(
        "pathways.Pathway", on_delete=models.SET_NULL, null=True, blank=True, related_name="registrations"
    )


class Award(models.Model):
    ATTENDANCE = "attendance"
    SKILL = "skill"
    CATEGORY_CHOICES = [
        (ATTENDANCE, "Attendance"),
        (SKILL, "Skill"),
    ]

    name = models.CharField(max_length=200)
    description = models.CharField(max_length=300, blank=True, default="")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    criteria = models.CharField(
        max_length=200, blank=True, default="", help_text='e.g. "Visited the dojo 10 times."'
    )

    def __str__(self):
        return self.name


class ParticipantAward(models.Model):
    participant = models.ForeignKey("accounts.Participant", on_delete=models.CASCADE, related_name="awards")
    award = models.ForeignKey(Award, on_delete=models.CASCADE, related_name="participant_awards")

    earned_date = models.DateField(null=True, blank=True, help_text="Blank if still in progress.")
    progress_current = models.PositiveIntegerField(null=True, blank=True)
    progress_total = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = [("participant", "award")]

    def __str__(self):
        return f"{self.participant} - {self.award}"
