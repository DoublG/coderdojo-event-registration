from django.db import models

from core.content_languages import OrganisationContent


class Skill(OrganisationContent):
    TRANSLATABLE_FIELDS = ("name",)

    """A single skill/topic a Pathway teaches, e.g. "Loops", "Conditionals"."""

    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Pathway(OrganisationContent):
    TRANSLATABLE_FIELDS = ("name", "subtitle", "description")

    name = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=300, blank=True, default="")
    description = models.TextField(blank=True, default="")
    image = models.ImageField(upload_to="pathways/", null=True, blank=True)

    min_age = models.PositiveSmallIntegerField(null=True, blank=True)
    max_age = models.PositiveSmallIntegerField(null=True, blank=True)
    no_experience_needed = models.BooleanField(default=True)
    runs_in_browser = models.BooleanField(default=False)

    skills = models.ManyToManyField(Skill, blank=True, related_name="pathways")

    def __str__(self):
        return self.name


class PathwayStepManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("pathway")


class PathwayStep(OrganisationContent):
    """One step of "how a session works" for a Pathway, in order."""

    TRANSLATABLE_FIELDS = ("title", "description")

    pathway = models.ForeignKey(Pathway, on_delete=models.CASCADE, related_name="steps")
    order = models.PositiveSmallIntegerField(default=0)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")

    objects = PathwayStepManager()

    class Meta:
        ordering = ["pathway", "order"]

    def __str__(self):
        return f"{self.pathway} step {self.order}: {self.title}"


class PathwayProjectManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("pathway")


class PathwayProject(OrganisationContent):
    """One example of "what you'll build" on a Pathway."""

    TRANSLATABLE_FIELDS = ("title", "description")

    pathway = models.ForeignKey(Pathway, on_delete=models.CASCADE, related_name="projects")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")

    objects = PathwayProjectManager()

    def __str__(self):
        return f"{self.pathway}: {self.title}"
