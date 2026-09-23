from django.test import TestCase
from django.urls import reverse

from .models import Pathway


class PathwayDetailViewTests(TestCase):
    def test_existing_pathway_renders_with_other_pathways(self):
        pathway = Pathway.objects.create(name="Scratch")
        other = Pathway.objects.create(name="Python")

        response = self.client.get(reverse("pathway_detail", kwargs={"pathway_id": pathway.id}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["pathway"], pathway)
        self.assertIn(other, response.context["other_pathways"])
        self.assertNotIn(pathway, response.context["other_pathways"])

    def test_missing_pathway_is_404(self):
        response = self.client.get(reverse("pathway_detail", kwargs={"pathway_id": 999999}))
        self.assertEqual(response.status_code, 404)
