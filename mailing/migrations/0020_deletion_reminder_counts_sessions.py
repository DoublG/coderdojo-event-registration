"""The account deletion reminder (privacy.retention) now says a child coming
to a dojo session also keeps the family's account (DATA_MODEL_PRIVACY.md §27).

load_mail_templates only creates templates, so this brings the existing rows
up to date, but only a row still exactly as it was seeded (its subject and
body match `old_sha256`): a template someone edited is left as it is.
"""

import hashlib

from django.db import migrations

UPDATES = [
    {
        "key": "account_deletion_reminder",
        "language": "en-us",
        "old_sha256": "82965854b7d27ff6b8b6ea7ec16fccd9cb62e4def31516c694d6cd1f76e537b7",
        "subject": "Your CoderDojo account will be deleted on {{ deletion_date|date:'j F Y' }}",
        "body": "Hi {{ recipient_name }},\n"
        "\n"
        "Nobody has logged in to your CoderDojo account for almost two years{% if children %}, and\n"
        "your children haven't used their own logins or come to a dojo session either{% endif %}. We don't "
        "keep data we no\n"
        'longer need, so on {{ deletion_date|date:"j F Y" }} your account will be\n'
        "{% if volunteer %}cleaned up.\n"
        "\n"
        "What stays: your name on the sessions you helped run and on the belts and badges you\n"
        "awarded{% if keeps_profile %}, and your profile on the dojos' team pages{% endif %}. Everything "
        "else goes: your\n"
        "login, your contact details, your applications and background-check details and your\n"
        "mail preferences.{% else %}deleted: your login, your contact details and your mail preferences.{% "
        "endif %}\n"
        "{% if children %}\n"
        "These children go with your account (their details, their own login if they have one,\n"
        "their belts and badges; the sessions they came to are kept without their name):\n"
        "{% for child in children %}- {{ child }}\n"
        "{% endfor %}{% endif %}{% if champion_of %}\n"
        "You're still the champion of {{ champion_of|join:\", \" }}. A dojo can't be without its\n"
        "champion, so your account stays until you hand that role to a mentor (on the dojo's\n"
        "Team page) or the organisation does.\n"
        "{% endif %}\n"
        "Want to keep your account? Just log in before that date{% if children %} (or let one of your\n"
        "children log in with their own login, or come to a dojo session){% endif %}:\n"
        "\n"
        "{{ login_url }}\n"
        "\n"
        "The CoderDojo Belgium team",
        "description": "An unused account will be deleted (privacy.retention). Variables: deletion_date, "
        "login_url, children, volunteer, keeps_profile, champion_of.",
    },
    {
        "key": "account_deletion_reminder",
        "language": "nl-be",
        "old_sha256": "da5d8d7caa27f7f9e0705fd79af14ad00776bc3f7cdc0d105209f6da3a3cf790",
        "subject": "Je CoderDojo-account wordt op {{ deletion_date|date:'j F Y' }} verwijderd",
        "body": "Hallo {{ recipient_name }},\n"
        "\n"
        "Er is al bijna twee jaar niet meer ingelogd op je CoderDojo-account{% if children %}, en ook je\n"
        "kinderen gebruikten hun eigen login niet en kwamen niet naar een dojosessie{% endif %}. We "
        "bewaren geen gegevens die we niet meer\n"
        'nodig hebben, dus op {{ deletion_date|date:"j F Y" }} wordt je account\n'
        "{% if volunteer %}opgeschoond.\n"
        "\n"
        "Wat blijft: je naam bij de sessies die je mee begeleidde en bij de gordels en badges die\n"
        "je uitreikte{% if keeps_profile %}, en je profiel op de teampagina's van de dojo's{% endif %}. Al "
        "de rest\n"
        "verdwijnt: je login, je contactgegevens, je aanvragen en de gegevens van je\n"
        "uittreksel uit het strafregister, en je mailvoorkeuren.{% else %}verwijderd: je login, je "
        "contactgegevens en je mailvoorkeuren.{% endif %}\n"
        "{% if children %}\n"
        "Deze kinderen verdwijnen mee met je account (hun gegevens, hun eigen login als ze er\n"
        "een hebben, hun gordels en badges; de sessies waar ze naartoe kwamen blijven bewaard\n"
        "zonder hun naam):\n"
        "{% for child in children %}- {{ child }}\n"
        "{% endfor %}{% endif %}{% if champion_of %}\n"
        'Je bent nog champion van {{ champion_of|join:", " }}. Een dojo kan niet zonder\n'
        "champion, dus je account blijft tot je die rol doorgeeft aan een mentor (op de\n"
        "Team-pagina van de dojo) of de organisatie dat doet.\n"
        "{% endif %}\n"
        "Wil je je account houden? Log dan gewoon in voor die datum{% if children %} (of laat een van je\n"
        "kinderen inloggen met de eigen login of naar een dojosessie komen){% endif %}:\n"
        "\n"
        "{{ login_url }}\n"
        "\n"
        "Het CoderDojo Belgium-team",
        "description": "An unused account will be deleted (privacy.retention). Variables: deletion_date, "
        "login_url, children, volunteer, keeps_profile, champion_of.",
    },
    {
        "key": "account_deletion_reminder",
        "language": "fr-be",
        "old_sha256": "7bb2ad5629f2f78af48643a3cf5315960d66de875649440f5e3d4838235deb48",
        "subject": "Votre compte CoderDojo sera supprimé le {{ deletion_date|date:'j F Y' }}",
        "body": "Bonjour {{ recipient_name }},\n"
        "\n"
        "Personne ne s'est connecté à votre compte CoderDojo depuis presque deux ans{% if children %}, et\n"
        "vos enfants n'ont pas non plus utilisé leur propre compte ni participé à une session de dojo{% "
        "endif %}. Nous ne gardons pas les\n"
        'données dont nous n\'avons plus besoin : le {{ deletion_date|date:"j F Y" }}, votre compte sera\n'
        "{% if volunteer %}nettoyé.\n"
        "\n"
        "Ce qui reste : votre nom sur les sessions que vous avez encadrées et sur les ceintures\n"
        "et badges que vous avez remis{% if keeps_profile %}, ainsi que votre profil sur les pages "
        "d'équipe des\n"
        "dojos{% endif %}. Tout le reste disparaît : votre connexion, vos coordonnées, vos candidatures\n"
        "et les données de votre extrait de casier judiciaire, et vos préférences d'e-mail.{% else "
        "%}supprimé : votre connexion, vos coordonnées et vos préférences d'e-mail.{% endif %}\n"
        "{% if children %}\n"
        "Ces enfants disparaissent avec votre compte (leurs données, leur propre compte s'ils en\n"
        "ont un, leurs ceintures et badges ; les sessions auxquelles ils ont participé sont\n"
        "gardées sans leur nom) :\n"
        "{% for child in children %}- {{ child }}\n"
        "{% endfor %}{% endif %}{% if champion_of %}\n"
        'Vous êtes toujours champion de {{ champion_of|join:", " }}. Un dojo ne peut pas rester\n'
        "sans champion : votre compte reste donc jusqu'à ce que vous passiez ce rôle à un\n"
        "mentor (sur la page Équipe du dojo) ou que l'organisation le fasse.\n"
        "{% endif %}\n"
        "Vous voulez garder votre compte ? Connectez-vous simplement avant cette date{% if children %} "
        "(ou\n"
        "laissez un de vos enfants se connecter avec son propre compte ou participer à une session de "
        "dojo){% endif %} :\n"
        "\n"
        "{{ login_url }}\n"
        "\n"
        "L'équipe CoderDojo Belgium",
        "description": "An unused account will be deleted (privacy.retention). Variables: deletion_date, "
        "login_url, children, volunteer, keeps_profile, champion_of.",
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
    dependencies = [("mailing", "0019_blocked_domain")]

    operations = [migrations.RunPython(update_templates, migrations.RunPython.noop)]
