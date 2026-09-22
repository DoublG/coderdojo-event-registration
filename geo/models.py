from django.contrib.gis.db import models


class AdministrativeBoundary(models.Model):
    COUNTRY = "country"
    PROVINCE = "province"
    KIND_CHOICES = [
        (COUNTRY, "Country"),
        (PROVINCE, "Province"),
    ]

    kind = models.CharField(max_length=10, choices=KIND_CHOICES, db_index=True)
    name = models.CharField(max_length=200)
    boundary = models.MultiPolygonField(srid=4326)

    def __str__(self):
        return self.name


class Municipality(models.Model):
    postal_code = models.CharField(max_length=10, db_index=True)
    name = models.CharField(max_length=200, db_index=True)

    center = models.PointField(srid=4326)

    def __str__(self):
        return f"{self.postal_code} {self.name}"
