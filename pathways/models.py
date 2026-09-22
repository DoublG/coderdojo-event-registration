from django.db import models


class Skill(models.Model):
    """A single skill/topic a Pathway teaches, e.g. "Loops", "Conditionals"."""

    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Pathway(models.Model):
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


class PathwayStep(models.Model):
    """One step of "how a session works" for a Pathway, in order."""

    pathway = models.ForeignKey(Pathway, on_delete=models.CASCADE, related_name="steps")
    order = models.PositiveSmallIntegerField(default=0)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["pathway", "order"]

    def __str__(self):
        return f"{self.pathway} step {self.order}: {self.title}"


class PathwayProject(models.Model):
    """One example of "what you'll build" on a Pathway."""

    pathway = models.ForeignKey(Pathway, on_delete=models.CASCADE, related_name="projects")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")

    def __str__(self):
        return f"{self.pathway}: {self.title}"
