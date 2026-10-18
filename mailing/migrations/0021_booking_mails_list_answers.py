"""The mails about a child's place (registration_confirmed,
registration_waitlisted, waitlist_promoted, session_reminder) list the
family's answers to the session's sign-up questions (DATA_MODEL.md §29): a
new `answers` variable. With no answers they read as before.

load_mail_templates only creates templates, so this brings the existing rows
up to date, but only a row still exactly as it was seeded (its subject and
body match `old_sha256`): a template someone edited is left as it is.
"""

import hashlib

from django.db import migrations

UPDATES = [{'key': 'registration_confirmed',
  'language': 'en-us',
  'old_sha256': 'de9a51799b3632db085129119134968eec2fc0b3eeafa305614da561d4a78306',
  'subject': '{{ ninja_name }} is signed up for {{ event_name }}',
  'body': 'Hi {{ recipient_name }},\n'
          '\n'
          '{{ ninja_name }} has a place at {{ event_name }} at {{ dojo_name }}.\n'
          '\n'
          '  When:  {{ start_time|date:"l j F Y" }}, {{ start_time|date:"H:i" }}–{{ end_time|date:"H:i" }}\n'
          '  Where: {{ venue }}\n'
          '{% if answers %}\n'
          'Your answers (you can change them on your account page until the session starts):\n'
          '{% for item in answers %}  {{ item.question }} {{ item.answer }}\n'
          '{% endfor %}{% endif %}\n'
          'Bring a charged laptop if you have one. The session details are here:\n'
          '{{ event_url }}\n'
          '\n'
          "Can't make it after all? Cancel from your account page, so someone on the\n"
          'waiting list gets the place: {{ account_url }}\n'
          '\n'
          'The CoderDojo Belgium team',
  'description': 'After signing a ninja up for a session with a free place. Variables: ninja_name, '
                 'event_name, dojo_name, start_time, end_time, venue, event_url, account_url, answers (the '
                 "sign-up questions' answers: question, answer)."},
 {'key': 'registration_confirmed',
  'language': 'nl-be',
  'old_sha256': '0f2f36c991aa2a326065d0a74e6f129dffc8ced6d62a271de2c1373c43b08861',
  'subject': '{{ ninja_name }} is ingeschreven voor {{ event_name }}',
  'body': 'Hallo {{ recipient_name }},\n'
          '\n'
          '{{ ninja_name }} heeft een plaats voor {{ event_name }} bij {{ dojo_name }}.\n'
          '\n'
          '  Wanneer: {{ start_time|date:"l j F Y" }}, {{ start_time|date:"H:i" }}–{{ end_time|date:"H:i" '
          '}}\n'
          '  Waar:    {{ venue }}\n'
          '{% if answers %}\n'
          'Je antwoorden (je kan ze tot de sessie begint wijzigen op je accountpagina):\n'
          '{% for item in answers %}  {{ item.question }} {{ item.answer }}\n'
          '{% endfor %}{% endif %}\n'
          'Breng een opgeladen laptop mee als je er een hebt. Alle details van de sessie:\n'
          '{{ event_url }}\n'
          '\n'
          'Toch verhinderd? Schrijf uit via je accountpagina, dan krijgt iemand van de\n'
          'wachtlijst de plaats: {{ account_url }}\n'
          '\n'
          'Het CoderDojo Belgium-team',
  'description': 'After signing a ninja up for a session with a free place. Variables: ninja_name, '
                 'event_name, dojo_name, start_time, end_time, venue, event_url, account_url, answers (the '
                 "sign-up questions' answers: question, answer)."},
 {'key': 'registration_confirmed',
  'language': 'fr-be',
  'old_sha256': '280749cf362abac146066885adeea9a220aa89ef7f95e8e61ace93a8d3756dab',
  'subject': '{{ ninja_name }} est inscrit·e à {{ event_name }}',
  'body': 'Bonjour {{ recipient_name }},\n'
          '\n'
          '{{ ninja_name }} a une place pour {{ event_name }} au {{ dojo_name }}.\n'
          '\n'
          '  Quand : {{ start_time|date:"l j F Y" }}, {{ start_time|date:"H:i" }}–{{ end_time|date:"H:i" }}\n'
          '  Où :    {{ venue }}\n'
          '{% if answers %}\n'
          "Vos réponses (modifiables sur votre page de compte jusqu'au début de la session) :\n"
          '{% for item in answers %}  {{ item.question }} {{ item.answer }}\n'
          '{% endfor %}{% endif %}\n'
          'Apportez un ordinateur portable chargé si vous en avez un. Tous les détails de la session :\n'
          '{{ event_url }}\n'
          '\n'
          'Un empêchement ? Annulez depuis votre page de compte pour libérer la place\n'
          "pour quelqu'un de la liste d'attente : {{ account_url }}\n"
          '\n'
          "L'équipe CoderDojo Belgium",
  'description': 'After signing a ninja up for a session with a free place. Variables: ninja_name, '
                 'event_name, dojo_name, start_time, end_time, venue, event_url, account_url, answers (the '
                 "sign-up questions' answers: question, answer)."},
 {'key': 'registration_waitlisted',
  'language': 'en-us',
  'old_sha256': '8f063dc1c13bd1034d8404c74c21c1cd14120f98270581bb4c966a24ea775b4a',
  'subject': '{{ ninja_name }} is on the waiting list for {{ event_name }}',
  'body': 'Hi {{ recipient_name }},\n'
          '\n'
          '{{ event_name }} at {{ dojo_name }} ({{ start_time|date:"l j F" }}) is full, so\n'
          '{{ ninja_name }} is on the waiting list. If a place comes free, it goes to whoever\n'
          "has waited longest, and we'll mail you straight away.\n"
          '{% if answers %}\n'
          'Your answers (you can change them on your account page until the session starts):\n'
          '{% for item in answers %}  {{ item.question }} {{ item.answer }}\n'
          '{% endfor %}{% endif %}\n'
          'Session details: {{ event_url }}\n'
          'Your registrations: {{ account_url }}\n'
          '\n'
          'The CoderDojo Belgium team',
  'description': "After signing a ninja up for a full session: they're on the waiting list. Variables: "
                 'ninja_name, event_name, dojo_name, start_time, event_url, account_url, answers (the '
                 "sign-up questions' answers: question, answer)."},
 {'key': 'registration_waitlisted',
  'language': 'nl-be',
  'old_sha256': 'd36b0c2dd39480c09cdeb326926e9af46c6c6e722e916435ba00f336bced7b4f',
  'subject': '{{ ninja_name }} staat op de wachtlijst voor {{ event_name }}',
  'body': 'Hallo {{ recipient_name }},\n'
          '\n'
          '{{ event_name }} bij {{ dojo_name }} ({{ start_time|date:"l j F" }}) is volzet, dus\n'
          '{{ ninja_name }} staat op de wachtlijst. Komt er een plaats vrij, dan gaat die naar\n'
          'wie het langst wacht, en mailen we je meteen.\n'
          '{% if answers %}\n'
          'Je antwoorden (je kan ze tot de sessie begint wijzigen op je accountpagina):\n'
          '{% for item in answers %}  {{ item.question }} {{ item.answer }}\n'
          '{% endfor %}{% endif %}\n'
          'Details van de sessie: {{ event_url }}\n'
          'Je inschrijvingen: {{ account_url }}\n'
          '\n'
          'Het CoderDojo Belgium-team',
  'description': "After signing a ninja up for a full session: they're on the waiting list. Variables: "
                 'ninja_name, event_name, dojo_name, start_time, event_url, account_url, answers (the '
                 "sign-up questions' answers: question, answer)."},
 {'key': 'registration_waitlisted',
  'language': 'fr-be',
  'old_sha256': 'df5dcfb05726ea39267b6e0377e40c4a8a38d529e1b0b8b918b799ecceb252dc',
  'subject': "{{ ninja_name }} est sur la liste d'attente pour {{ event_name }}",
  'body': 'Bonjour {{ recipient_name }},\n'
          '\n'
          '{{ event_name }} au {{ dojo_name }} ({{ start_time|date:"l j F" }}) est complet :\n'
          "{{ ninja_name }} est donc sur la liste d'attente. Si une place se libère, elle va à\n"
          'la personne qui attend depuis le plus longtemps, et nous vous écrivons aussitôt.\n'
          '{% if answers %}\n'
          "Vos réponses (modifiables sur votre page de compte jusqu'au début de la session) :\n"
          '{% for item in answers %}  {{ item.question }} {{ item.answer }}\n'
          '{% endfor %}{% endif %}\n'
          'Détails de la session : {{ event_url }}\n'
          'Vos inscriptions : {{ account_url }}\n'
          '\n'
          "L'équipe CoderDojo Belgium",
  'description': "After signing a ninja up for a full session: they're on the waiting list. Variables: "
                 'ninja_name, event_name, dojo_name, start_time, event_url, account_url, answers (the '
                 "sign-up questions' answers: question, answer)."},
 {'key': 'waitlist_promoted',
  'language': 'en-us',
  'old_sha256': 'a00c5ec3e8dc708170d057a457fe5af960ac59a6de0b760268405d966552ec57',
  'subject': 'Good news: {{ ninja_name }} has a place at {{ event_name }}',
  'body': 'Hi {{ recipient_name }},\n'
          '\n'
          'A place came free at {{ event_name }} at {{ dojo_name }}, and {{ ninja_name }} was\n'
          'next on the waiting list, so the place is theirs.\n'
          '\n'
          'The session starts on {{ start_time|date:"l j F" }} at {{ start_time|date:"H:i" }}: {{ event_url '
          '}}\n'
          '{% if answers %}\n'
          'Your answers (you can change them on your account page until the session starts):\n'
          '{% for item in answers %}  {{ item.question }} {{ item.answer }}\n'
          '{% endfor %}{% endif %}\n'
          "If {{ ninja_name }} can't come any more, please cancel on your account page so the\n"
          'next person gets the place: {{ account_url }}\n'
          '\n'
          'The CoderDojo Belgium team',
  'description': 'A place came free and a waitlisted ninja moved up. Variables: ninja_name, event_name, '
                 "dojo_name, start_time, event_url, account_url, answers (the sign-up questions' answers: "
                 'question, answer).'},
 {'key': 'waitlist_promoted',
  'language': 'nl-be',
  'old_sha256': 'f73b8d672688554d6809433772e6f9eab7e3cccfbf0f02f111c6b1e7a02f819e',
  'subject': 'Goed nieuws: {{ ninja_name }} heeft een plaats voor {{ event_name }}',
  'body': 'Hallo {{ recipient_name }},\n'
          '\n'
          'Er is een plaats vrijgekomen voor {{ event_name }} bij {{ dojo_name }}, en\n'
          '{{ ninja_name }} stond als eerste op de wachtlijst. De plaats is dus voor jullie.\n'
          '\n'
          'De sessie begint op {{ start_time|date:"l j F" }} om {{ start_time|date:"H:i" }}: {{ event_url '
          '}}\n'
          '{% if answers %}\n'
          'Je antwoorden (je kan ze tot de sessie begint wijzigen op je accountpagina):\n'
          '{% for item in answers %}  {{ item.question }} {{ item.answer }}\n'
          '{% endfor %}{% endif %}\n'
          'Kan {{ ninja_name }} niet meer komen? Schrijf dan uit via je accountpagina, zodat\n'
          'de volgende op de lijst de plaats krijgt: {{ account_url }}\n'
          '\n'
          'Het CoderDojo Belgium-team',
  'description': 'A place came free and a waitlisted ninja moved up. Variables: ninja_name, event_name, '
                 "dojo_name, start_time, event_url, account_url, answers (the sign-up questions' answers: "
                 'question, answer).'},
 {'key': 'waitlist_promoted',
  'language': 'fr-be',
  'old_sha256': '34a3f02b8a790fd58ebb744c5d5006116d45b4fb44b8a323dfa9da57164592fd',
  'subject': 'Bonne nouvelle : {{ ninja_name }} a une place pour {{ event_name }}',
  'body': 'Bonjour {{ recipient_name }},\n'
          '\n'
          "Une place s'est libérée pour {{ event_name }} au {{ dojo_name }}, et {{ ninja_name }}\n"
          "était en tête de la liste d'attente : la place est pour vous.\n"
          '\n'
          'La session commence le {{ start_time|date:"l j F" }} à {{ start_time|date:"H:i" }} : {{ event_url '
          '}}\n'
          '{% if answers %}\n'
          "Vos réponses (modifiables sur votre page de compte jusqu'au début de la session) :\n"
          '{% for item in answers %}  {{ item.question }} {{ item.answer }}\n'
          '{% endfor %}{% endif %}\n'
          'Si {{ ninja_name }} ne peut plus venir, annulez depuis votre page de compte pour\n'
          'que la personne suivante reçoive la place : {{ account_url }}\n'
          '\n'
          "L'équipe CoderDojo Belgium",
  'description': 'A place came free and a waitlisted ninja moved up. Variables: ninja_name, event_name, '
                 "dojo_name, start_time, event_url, account_url, answers (the sign-up questions' answers: "
                 'question, answer).'},
 {'key': 'session_reminder',
  'language': 'en-us',
  'old_sha256': '003d4d540c3417bafb1bde49ff94b89b50f7a675e4a15049ada5eec68013a1da',
  'subject': "Reminder: {{ event_name }} on {{ start_time|date:'l' }}",
  'body': 'Hi {{ recipient_name }},\n'
          '\n'
          'A quick reminder that {{ ninja_name }} is coming to {{ event_name }} at {{ dojo_name }}:\n'
          '\n'
          '  {{ start_time|date:"l j F" }}, {{ start_time|date:"H:i" }}–{{ end_time|date:"H:i" }}\n'
          '  {{ venue }}\n'
          '\n'
          'Details: {{ event_url }}\n'
          '{% if answers %}\n'
          'Your answers (you can change them on your account page until the session starts):\n'
          '{% for item in answers %}  {{ item.question }} {{ item.answer }}\n'
          '{% endfor %}{% endif %}\n'
          'Plans changed? Cancel on your account page and the place goes to the waiting\n'
          'list: {{ account_url }}\n'
          '\n'
          'The CoderDojo Belgium team\n'
          '\n'
          '--\n'
          'You get this mail because of your mail preferences. Unsubscribe: {{ unsubscribe_url }}',
  'description': 'Two days before a session, for every confirmed registration. Variables: ninja_name, '
                 'event_name, dojo_name, start_time, end_time, venue, event_url, account_url, answers (the '
                 "sign-up questions' answers: question, answer)."},
 {'key': 'session_reminder',
  'language': 'nl-be',
  'old_sha256': '4c21d930acba06609f00801b6f23c8ef908904e46512bf7e348e3dde69b7b1b2',
  'subject': "Herinnering: {{ event_name }} op {{ start_time|date:'l' }}",
  'body': 'Hallo {{ recipient_name }},\n'
          '\n'
          'Een korte herinnering: {{ ninja_name }} komt naar {{ event_name }} bij {{ dojo_name }}.\n'
          '\n'
          '  {{ start_time|date:"l j F" }}, {{ start_time|date:"H:i" }}–{{ end_time|date:"H:i" }}\n'
          '  {{ venue }}\n'
          '\n'
          'Details: {{ event_url }}\n'
          '{% if answers %}\n'
          'Je antwoorden (je kan ze tot de sessie begint wijzigen op je accountpagina):\n'
          '{% for item in answers %}  {{ item.question }} {{ item.answer }}\n'
          '{% endfor %}{% endif %}\n'
          'Plannen gewijzigd? Schrijf uit via je accountpagina, dan gaat de plaats naar de\n'
          'wachtlijst: {{ account_url }}\n'
          '\n'
          'Het CoderDojo Belgium-team\n'
          '\n'
          '--\n'
          'Je krijgt deze mail door je mailvoorkeuren. Uitschrijven: {{ unsubscribe_url }}',
  'description': 'Two days before a session, for every confirmed registration. Variables: ninja_name, '
                 'event_name, dojo_name, start_time, end_time, venue, event_url, account_url, answers (the '
                 "sign-up questions' answers: question, answer)."},
 {'key': 'session_reminder',
  'language': 'fr-be',
  'old_sha256': '46e46ab28c46d9a1b6f048f74c5b1e49472697cd90e8d8e18f0859be0b284f6d',
  'subject': "Rappel : {{ event_name }} ce {{ start_time|date:'l' }}",
  'body': 'Bonjour {{ recipient_name }},\n'
          '\n'
          'Petit rappel : {{ ninja_name }} participe à {{ event_name }} au {{ dojo_name }}.\n'
          '\n'
          '  {{ start_time|date:"l j F" }}, {{ start_time|date:"H:i" }}–{{ end_time|date:"H:i" }}\n'
          '  {{ venue }}\n'
          '\n'
          'Détails : {{ event_url }}\n'
          '{% if answers %}\n'
          "Vos réponses (modifiables sur votre page de compte jusqu'au début de la session) :\n"
          '{% for item in answers %}  {{ item.question }} {{ item.answer }}\n'
          '{% endfor %}{% endif %}\n'
          'Changement de programme ? Annulez depuis votre page de compte et la place ira à\n'
          "la liste d'attente : {{ account_url }}\n"
          '\n'
          "L'équipe CoderDojo Belgium\n"
          '\n'
          '--\n'
          'Vous recevez ce mail selon vos préférences. Se désabonner : {{ unsubscribe_url }}',
  'description': 'Two days before a session, for every confirmed registration. Variables: ninja_name, '
                 'event_name, dojo_name, start_time, end_time, venue, event_url, account_url, answers (the '
                 "sign-up questions' answers: question, answer)."}]


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
