from django.db import models


class CapacitySample(models.Model):
    """One day's measurement of the site's components (monitoring.tasks,
    CAPACITY.md): table sizes, MySQL's and Redis's counters, the queues and
    each process's memory, as `data`. Taken daily so growth shows as a
    trend; nothing about any person."""

    taken_on = models.DateField(unique=True)
    taken_at = models.DateTimeField()
    data = models.JSONField(default=dict)

    class Meta:
        ordering = ["-taken_on"]

    def __str__(self):
        return f"Capacity sample {self.taken_on}"

    @property
    def database_bytes(self):
        return sum(t["data_bytes"] + t["index_bytes"] for t in self.data.get("tables", {}).values())
