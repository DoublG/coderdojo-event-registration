from django.test import TestCase
from django.urls import reverse

from content.models import Testimonial
from dojos.models import Dojo
from pathways.models import Pathway


class HomeViewTests(TestCase):
    def test_empty_site_renders(self):
        """The homepage composes widgets from several apps — none of them
        should assume there's at least one row to work with."""
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/home.html")

    def test_populated_site_renders(self):
        Pathway.objects.create(name="Scratch")
        Dojo.objects.create(name="Ghent")
        Testimonial.objects.create(quote="Great!", author="A parent")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["pathways"]), 1)
        self.assertIsNotNone(response.context["testimonial"])
