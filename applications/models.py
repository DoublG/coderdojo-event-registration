from django.db import models


class DojoApplication(models.Model):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (APPROVED, "Approved"),
        (REJECTED, "Rejected"),
    ]

    applicant_name = models.CharField(max_length=200)
    applicant_email = models.EmailField()
    applicant_phone = models.CharField(max_length=30, blank=True, default="")
    area = models.CharField(max_length=200, help_text="City/area where the dojo would run.")
    preferred_schedule = models.CharField(max_length=200, blank=True, default="", help_text='e.g. "Saturday mornings"')
    proposed_venue = models.CharField(max_length=200, blank=True, default="")
    message = models.TextField(blank=True, default="")
    consent = models.BooleanField(default=False, help_text="Understands sessions are free and volunteer-run.")

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.applicant_name} - {self.area}"


class MentorApplication(models.Model):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (APPROVED, "Approved"),
        (REJECTED, "Rejected"),
    ]

    VOLUNTEER_MENTOR = "volunteer_mentor"
    OTHER = "other"
    ROLE_CHOICES = [
        (VOLUNTEER_MENTOR, "Volunteer mentor"),
        (OTHER, "Something else (board, events, comms)"),
    ]

    applicant_name = models.CharField(max_length=200)
    applicant_email = models.EmailField()
    applicant_phone = models.CharField(max_length=30, blank=True, default="")
    dojo = models.ForeignKey(
        "dojos.Dojo", on_delete=models.SET_NULL, null=True, blank=True, related_name="mentor_applications",
        help_text="Blank if the applicant is open to any dojo.",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=VOLUNTEER_MENTOR)
    about = models.TextField(blank=True, default="", help_text="Applicant's skills/interests.")
    background_check_consent = models.BooleanField(default=False)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.applicant_name} ({self.get_role_display()})"
