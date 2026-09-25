from unittest.mock import AsyncMock, Mock, patch

from django.test import TestCase

from dojos.models import Dojo
from dojos.testing import make_champion, make_dojo

from .models import Notification
from .services import notify


class NotifyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = make_champion(username="owner1", email="owner@example.com")
        cls.dojo = make_dojo("Ghent", champion=cls.owner)

    def test_creates_notification_row(self):
        notification = notify(self.owner, "Something happened.", url="/somewhere/", dojo=self.dojo)

        self.assertEqual(notification.recipient, self.owner)
        self.assertEqual(notification.text, "Something happened.")
        self.assertEqual(notification.url, "/somewhere/")
        self.assertEqual(notification.dojo, self.dojo)
        self.assertFalse(notification.read)
        self.assertEqual(Notification.objects.count(), 1)

    def test_text_is_written_in_the_recipients_language(self):
        """Stored as shown, so rendered in the recipient's own language, whoever
        triggered it (notifications.services.notify, `params`)."""
        from django.utils import translation
        from django.utils.translation import gettext_lazy

        self.owner.preferred_language = "nl-be"
        self.owner.save(update_fields=["preferred_language"])
        with translation.override("fr-be"):
            notification = notify(self.owner, gettext_lazy("You've been added to the %(dojo)s team."), params={"dojo": "Ghent"})
        self.assertEqual(notification.text, "Je bent toegevoegd aan het team van Ghent.")

    def test_publishes_to_the_recipients_group(self):
        with patch("notifications.services.get_channel_layer") as mock_get_layer:
            mock_layer = Mock()
            mock_layer.group_send = AsyncMock()
            mock_get_layer.return_value = mock_layer
            notify(self.owner, "Something happened.", dojo=self.dojo)

        mock_layer.group_send.assert_called_once()
        group_name, event = mock_layer.group_send.call_args[0]
        self.assertEqual(group_name, f"notifications_user_{self.owner.id}")
        self.assertEqual(event, {"type": "notification.push"})

    def test_channel_layer_failure_does_not_block_the_notification(self):
        """The DB row is the source of truth — a Redis hiccup (or, as in
        this test environment, no Redis at all) must never raise out of
        notify() and break whatever action triggered it."""
        with patch("notifications.services.get_channel_layer") as mock_get_layer:
            mock_layer = Mock()
            mock_layer.group_send = AsyncMock(side_effect=RuntimeError("redis is down"))
            mock_get_layer.return_value = mock_layer
            notification = notify(self.owner, "Still saved.", dojo=self.dojo)

        self.assertEqual(notification.text, "Still saved.")
        self.assertTrue(Notification.objects.filter(text="Still saved.").exists())

    def test_no_channel_layer_configured_does_not_block_the_notification(self):
        with patch("notifications.services.get_channel_layer", return_value=None):
            notification = notify(self.owner, "No layer configured.", dojo=self.dojo)

        self.assertTrue(Notification.objects.filter(pk=notification.pk).exists())

    def test_works_against_the_real_configured_channel_layer(self):
        """No mocking — exercises whatever website.settings.CHANNEL_LAYERS
        actually points at (Redis, in every environment this repo runs
        in). Mainly documents that notify() must keep working here too,
        not just against the mocked/fail-open paths above — if this
        starts failing, either Redis isn't reachable (see the workflow
        rule on always running inside .devcontainer) or something broke
        the real group_send() call."""
        notification = notify(self.owner, "Real call, real channel layer.", dojo=self.dojo)
        self.assertTrue(Notification.objects.filter(pk=notification.pk).exists())
