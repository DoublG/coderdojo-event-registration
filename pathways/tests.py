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



class SeededPathwaysTests(TestCase):
    """seed_pathways: the nine pathways, with the Raspberry Pi pathway also
    covering Arduino and ESP32, shown in the visitor's language."""

    @classmethod
    def setUpTestData(cls):
        from io import StringIO

        from django.core.management import call_command

        call_command("seed_pathways", stdout=StringIO())
        call_command("seed_content_languages", stdout=StringIO())

    def test_new_pathways_exist(self):
        names = set(Pathway.objects.values_list("name", flat=True))
        self.assertTrue({"mBot", "Sonic Pi", "Unity"} <= names)
        self.assertEqual(len(names), 9)

    def test_raspberry_pi_page_covers_arduino_and_esp32(self):
        pathway = Pathway.objects.get(name="Raspberry Pi (physical computing)")
        url = reverse("pathway_detail", kwargs={"pathway_id": pathway.id})
        english = self.client.get(url)
        self.assertContains(english, "About this pathway")
        self.assertContains(english, "an ESP32 adds Wi-Fi")
        self.assertContains(english, "A plant-watering alarm with Arduino")
        dutch = self.client.get(url, HTTP_ACCEPT_LANGUAGE="nl-be")
        self.assertContains(dutch, "een ESP32 heeft daarbovenop wifi")
        self.assertContains(dutch, "Raspberry Pi, Arduino of ESP32: wat is het verschil?")

    def test_rerun_keeps_translations_in_step(self):
        from io import StringIO

        from django.core.management import call_command

        call_command("seed_pathways", stdout=StringIO())
        call_command("seed_content_languages", stdout=StringIO())
        unity = Pathway.objects.get(name="Unity")
        self.assertEqual(unity.translation_for("fr-be", "subtitle"), "Créez vos propres jeux 2D et 3D avec un vrai moteur de jeu.")
        self.assertEqual(Pathway.objects.count(), 9)
