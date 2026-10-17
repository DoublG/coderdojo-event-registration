"""The booking mails (registration_confirmed, registration_waitlisted) list
the family's answers to the session's sign-up questions (DATA_MODEL.md §29,
phase 2): a new `answers` variable. With no answers they read as before.

load_mail_templates only creates templates, so this brings the existing rows
up to date, but only a row still exactly as it was seeded (its subject and
body match `old_sha256`): a template someone edited is left as it is.
"""

import hashlib

from django.db import migrations

UPDATES = [
    {
        "key": "registration_confirmed",
        "language": "en-us",
        "old_sha256": "de9a51799b3632db085129119134968eec2fc0b3eeafa305614da561d4a78306",
        "subject": "{{ ninja_name }} is signed up for {{ event_name }}",
        "body": "Hi {{ recipient_name }},\n"
        "\n"
        "{{ ninja_name }} has a place at {{ event_name }} at {{ dojo_name }}.\n"
        "\n"
        '  When:  {{ start_time|date:"l j F Y" }}, {{ start_time|date:"H:i" }}–{{ end_time|date:"H:i" }}\n'
        "  Where: {{ venue }}\n"
        "{% if answers %}\n"
        "Your answers (you can change them on your account page until the session starts):\n"
        "{% for item in answers %}  {{ item.question }} {{ item.answer }}\n"
        "{% endfor %}{% endif %}\n"
        "Bring a charged laptop if you have one. The session details are here:\n"
        "{{ event_url }}\n"
        "\n"
        "Can't make it after all? Cancel from your account page, so someone on the\n"
        "waiting list gets the place: {{ account_url }}\n"
        "\n"
        "The CoderDojo Belgium team",
        "description": "After signing a ninja up for a session with a free place. Variables: ninja_name, "
        "event_name, dojo_name, start_time, end_time, venue, event_url, account_url, answers (the "
        "sign-up questions' answers: question, answer).",
    },
    {
        "key": "registration_confirmed",
        "language": "nl-be",
        "old_sha256": "0f2f36c991aa2a326065d0a74e6f129dffc8ced6d62a271de2c1373c43b08861",
        "subject": "{{ ninja_name }} is ingeschreven voor {{ event_name }}",
        "body": "Hallo {{ recipient_name }},\n"
        "\n"
        "{{ ninja_name }} heeft een plaats voor {{ event_name }} bij {{ dojo_name }}.\n"
        "\n"
        '  Wanneer: {{ start_time|date:"l j F Y" }}, {{ start_time|date:"H:i" }}–{{ end_time|date:"H:i" '
        "}}\n"
        "  Waar:    {{ venue }}\n"
        "{% if answers %}\n"
        "Je antwoorden (je kan ze tot de sessie begint wijzigen op je accountpagina):\n"
        "{% for item in answers %}  {{ item.question }} {{ item.answer }}\n"
        "{% endfor %}{% endif %}\n"
        "Breng een opgeladen laptop mee als je er een hebt. Alle details van de sessie:\n"
        "{{ event_url }}\n"
        "\n"
        "Toch verhinderd? Schrijf uit via je accountpagina, dan krijgt iemand van de\n"
        "wachtlijst de plaats: {{ account_url }}\n"
        "\n"
        "Het CoderDojo Belgium-team",
        "description": "After signing a ninja up for a session with a free place. Variables: ninja_name, "
        "event_name, dojo_name, start_time, end_time, venue, event_url, account_url, answers (the "
        "sign-up questions' answers: question, answer).",
    },
    {
        "key": "registration_confirmed",
        "language": "fr-be",
        "old_sha256": "280749cf362abac146066885adeea9a220aa89ef7f95e8e61ace93a8d3756dab",
        "subject": "{{ ninja_name }} est inscrit·e à {{ event_name }}",
        "body": "Bonjour {{ recipient_name }},\n"
        "\n"
        "{{ ninja_name }} a une place pour {{ event_name }} au {{ dojo_name }}.\n"
        "\n"
        '  Quand : {{ start_time|date:"l j F Y" }}, {{ start_time|date:"H:i" }}–{{ end_time|date:"H:i" }}\n'
        "  Où :    {{ venue }}\n"
        "{% if answers %}\n"
        "Vos réponses (modifiables sur votre page de compte jusqu'au début de la session) :\n"
        "{% for item in answers %}  {{ item.question }} {{ item.answer }}\n"
        "{% endfor %}{% endif %}\n"
        "Apportez un ordinateur portable chargé si vous en avez un. Tous les détails de la session :\n"
        "{{ event_url }}\n"
        "\n"
        "Un empêchement ? Annulez depuis votre page de compte pour libérer la place\n"
        "pour quelqu'un de la liste d'attente : {{ account_url }}\n"
        "\n"
        "L'équipe CoderDojo Belgium",
        "description": "After signing a ninja up for a session with a free place. Variables: ninja_name, "
        "event_name, dojo_name, start_time, end_time, venue, event_url, account_url, answers (the "
        "sign-up questions' answers: question, answer).",
    },
    {
        "key": "registration_waitlisted",
        "language": "en-us",
        "old_sha256": "8f063dc1c13bd1034d8404c74c21c1cd14120f98270581bb4c966a24ea775b4a",
        "subject": "{{ ninja_name }} is on the waiting list for {{ event_name }}",
        "body": "Hi {{ recipient_name }},\n"
        "\n"
        '{{ event_name }} at {{ dojo_name }} ({{ start_time|date:"l j F" }}) is full, so\n'
        "{{ ninja_name }} is on the waiting list. If a place comes free, it goes to whoever\n"
        "has waited longest, and we'll mail you straight away.\n"
        "{% if answers %}\n"
        "Your answers (you can change them on your account page until the session starts):\n"
        "{% for item in answers %}  {{ item.question }} {{ item.answer }}\n"
        "{% endfor %}{% endif %}\n"
        "Session details: {{ event_url }}\n"
        "Your registrations: {{ account_url }}\n"
        "\n"
        "The CoderDojo Belgium team",
        "description": "After signing a ninja up for a full session: they're on the waiting list. Variables: "
        "ninja_name, event_name, dojo_name, start_time, event_url, account_url, answers (the "
        "sign-up questions' answers: question, answer).",
    },
    {
        "key": "registration_waitlisted",
        "language": "nl-be",
        "old_sha256": "d36b0c2dd39480c09cdeb326926e9af46c6c6e722e916435ba00f336bced7b4f",
        "subject": "{{ ninja_name }} staat op de wachtlijst voor {{ event_name }}",
        "body": "Hallo {{ recipient_name }},\n"
        "\n"
        '{{ event_name }} bij {{ dojo_name }} ({{ start_time|date:"l j F" }}) is volzet, dus\n'
        "{{ ninja_name }} staat op de wachtlijst. Komt er een plaats vrij, dan gaat die naar\n"
        "wie het langst wacht, en mailen we je meteen.\n"
        "{% if answers %}\n"
        "Je antwoorden (je kan ze tot de sessie begint wijzigen op je accountpagina):\n"
        "{% for item in answers %}  {{ item.question }} {{ item.answer }}\n"
        "{% endfor %}{% endif %}\n"
        "Details van de sessie: {{ event_url }}\n"
        "Je inschrijvingen: {{ account_url }}\n"
        "\n"
        "Het CoderDojo Belgium-team",
        "description": "After signing a ninja up for a full session: they're on the waiting list. Variables: "
        "ninja_name, event_name, dojo_name, start_time, event_url, account_url, answers (the "
        "sign-up questions' answers: question, answer).",
    },
    {
        "key": "registration_waitlisted",
        "language": "fr-be",
        "old_sha256": "df5dcfb05726ea39267b6e0377e40c4a8a38d529e1b0b8b918b799ecceb252dc",
        "subject": "{{ ninja_name }} est sur la liste d'attente pour {{ event_name }}",
        "body": "Bonjour {{ recipient_name }},\n"
        "\n"
        '{{ event_name }} au {{ dojo_name }} ({{ start_time|date:"l j F" }}) est complet :\n'
        "{{ ninja_name }} est donc sur la liste d'attente. Si une place se libère, elle va à\n"
        "la personne qui attend depuis le plus longtemps, et nous vous écrivons aussitôt.\n"
        "{% if answers %}\n"
        "Vos réponses (modifiables sur votre page de compte jusqu'au début de la session) :\n"
        "{% for item in answers %}  {{ item.question }} {{ item.answer }}\n"
        "{% endfor %}{% endif %}\n"
        "Détails de la session : {{ event_url }}\n"
        "Vos inscriptions : {{ account_url }}\n"
        "\n"
        "L'équipe CoderDojo Belgium",
        "description": "After signing a ninja up for a full session: they're on the waiting list. Variables: "
        "ninja_name, event_name, dojo_name, start_time, event_url, account_url, answers (the "
        "sign-up questions' answers: question, answer).",
    },
]


def update_templates(apps, schema_editor):
    EmailTemplate = apps.get_model("mailing", "EmailTemplate")
    for update in UPDATES:
        row = EmailTemplate.objects.filter(key=update["key"], language=update["language"]).first()
        if row is None:
            continue  # load_mail_templates creates it with the new text
        seen = hashlib.sha256((row.subject + "\x00" + row.body).encode()).hexdigest()
        if seen != update["old_sha256"]:
            continue  # edited by someone: theirs to update
        row.subject, row.body, row.description = update["subject"], update["body"], update["description"]
        row.save(update_fields=["subject", "body", "description"])


class Migration(migrations.Migration):
    dependencies = [("mailing", "0020_deletion_reminder_counts_sessions")]

    operations = [migrations.RunPython(update_templates, migrations.RunPython.noop)]
