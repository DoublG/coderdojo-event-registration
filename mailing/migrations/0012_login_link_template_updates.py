"""The mail templates that changed for login links and children's logins
(DATA_MODEL.md §24): the child's first mail (a password or a login link), an
email change a guardian started, and two-step login turned off by a guardian.

load_mail_templates only creates templates, so this brings the existing rows
up to date, but only a row still exactly as it was seeded (its subject and
body match `old_sha256`): a template someone edited is left as it is.
"""

import hashlib

from django.db import migrations

UPDATES = [
    {
        "key": "email_change_confirm",
        "language": "en-us",
        "old_sha256": "677ed32d31fa8975c1a2bbbfda50e74ef4afecf87c16e5c1cd41eb97f474dea6",
        "subject": "Confirm your new email address",
        "body": "Hi {{ recipient_name }},\n"
        "\n"
        "{% if by_guardian %}{{ by_guardian }} is changing the email address of your CoderDojo login from "
        "{{ old_email }} to {{ new_email }}.{% elif by_organisation %}At your request, CoderDojo Belgium "
        "is changing the email address of your CoderDojo account from {{ old_email }} to {{ new_email "
        "}}.{% else %}You asked to change the email address of your CoderDojo account from {{ old_email }} "
        "to {{ new_email }}.{% endif %}\n"
        "\n"
        "To confirm, open this link within {{ valid_hours }} hours:\n"
        "\n"
        "{{ confirm_url }}\n"
        "\n"
        "Nothing changes until you do. If you didn't ask for this, you can ignore this email.\n"
        "\n"
        "The CoderDojo Belgium team",
        "description": "Sent to the NEW address when someone asks to change the account's email "
        "(accounts/email_change.py). Variables: new_email, old_email, confirm_url, valid_hours, "
        "by_organisation, by_guardian (a guardian's name, for a child's login).",
    },
    {
        "key": "email_change_confirm",
        "language": "fr-be",
        "old_sha256": "38713a0a48a0d16c608a07f18a461b332512e0f6bb97f0628566ee512aee6f29",
        "subject": "Confirmez votre nouvelle adresse e-mail",
        "body": "Bonjour {{ recipient_name }},\n"
        "\n"
        "{% if by_guardian %}{{ by_guardian }} change l'adresse e-mail de votre connexion CoderDojo : {{ "
        "old_email }} devient {{ new_email }}.{% elif by_organisation %}À votre demande, CoderDojo Belgium "
        "change l'adresse e-mail de votre compte CoderDojo : {{ old_email }} devient {{ new_email }}.{% "
        "else %}Vous avez demandé à changer l'adresse e-mail de votre compte CoderDojo : {{ old_email }} "
        "devient {{ new_email }}.{% endif %}\n"
        "\n"
        "Pour confirmer, ouvrez ce lien dans les {{ valid_hours }} heures :\n"
        "\n"
        "{{ confirm_url }}\n"
        "\n"
        "Rien ne change avant cela. Si vous n'avez rien demandé, vous pouvez ignorer cet e-mail.\n"
        "\n"
        "L'équipe CoderDojo Belgium",
        "description": "Sent to the NEW address when someone asks to change the account's email "
        "(accounts/email_change.py). Variables: new_email, old_email, confirm_url, valid_hours, "
        "by_organisation, by_guardian (a guardian's name, for a child's login).",
    },
    {
        "key": "email_change_confirm",
        "language": "nl-be",
        "old_sha256": "741b80faaa43cef6563a99203b7c325e0d1bc06879f27c9d4b704244d85abea6",
        "subject": "Bevestig je nieuwe e-mailadres",
        "body": "Hallo {{ recipient_name }},\n"
        "\n"
        "{% if by_guardian %}{{ by_guardian }} wijzigt het e-mailadres van je CoderDojo-login van {{ "
        "old_email }} naar {{ new_email }}.{% elif by_organisation %}Op jouw vraag wijzigt CoderDojo "
        "Belgium het e-mailadres van je CoderDojo-account van {{ old_email }} naar {{ new_email }}.{% else "
        "%}Je vroeg om het e-mailadres van je CoderDojo-account te wijzigen van {{ old_email }} naar {{ "
        "new_email }}.{% endif %}\n"
        "\n"
        "Open deze link binnen {{ valid_hours }} uur om het te bevestigen:\n"
        "\n"
        "{{ confirm_url }}\n"
        "\n"
        "Tot dan verandert er niets. Heb je dit niet gevraagd? Dan kan je deze e-mail negeren.\n"
        "\n"
        "Het CoderDojo Belgium-team",
        "description": "Sent to the NEW address when someone asks to change the account's email "
        "(accounts/email_change.py). Variables: new_email, old_email, confirm_url, valid_hours, "
        "by_organisation, by_guardian (a guardian's name, for a child's login).",
    },
    {
        "key": "ninja_account_created",
        "language": "en-us",
        "old_sha256": "ef4ea55ce3b3751e104d3502a2c134dbf863d1f0bb42de6875779b95d928406d",
        "subject": "Your own CoderDojo login",
        "body": "Hi {{ recipient_name }},\n"
        "\n"
        "{{ guardian_name }} made you your own CoderDojo login. With it you can see your belt,\n"
        "your badges and the sessions you've been to, and sign yourself up for sessions.\n"
        "\n"
        "{% if uses_link %}You log in with a link we mail you, so there's no password to remember. Open "
        "this link within {{ valid_days }} days to log in for the first time:\n"
        "\n"
        "{{ login_url }}\n"
        "\n"
        'Next time, enter this email address on the login page and choose "Log in with an emailed link".{% '
        "else %}Choose your password here:\n"
        "\n"
        "{{ set_password_url }}\n"
        "\n"
        "After that, log in with this email address (or your username, {{ username }}).{% endif %}\n"
        "\n"
        "Didn't expect this mail? Then you can ignore it.\n"
        "\n"
        "The CoderDojo Belgium team",
        "description": "A guardian gave their child their own login (or switched it back on). Sent to the child's "
        "address. Variables: guardian_name, username, uses_link, set_password_url or login_url, "
        "valid_days.",
    },
    {
        "key": "ninja_account_created",
        "language": "fr-be",
        "old_sha256": "1e61187fea68a20b123df2059688c197ea73caf2b8d58d4ecd9929f769c73f63",
        "subject": "Ton propre compte CoderDojo",
        "body": "Bonjour {{ recipient_name }},\n"
        "\n"
        "{{ guardian_name }} t'a créé ton propre compte CoderDojo. Tu peux y voir ta ceinture,\n"
        "tes badges et les sessions auxquelles tu as participé, et t'inscrire toi-même à des\n"
        "sessions.\n"
        "\n"
        "{% if uses_link %}Tu te connectes avec un lien que nous t'envoyons par e-mail : pas de mot de "
        "passe à retenir. Ouvre ce lien dans les {{ valid_days }} jours pour te connecter la première fois "
        ":\n"
        "\n"
        "{{ login_url }}\n"
        "\n"
        "La prochaine fois, entre cette adresse e-mail sur la page de connexion et choisis « Se connecter "
        "avec un lien par e-mail ».{% else %}Choisis ton mot de passe ici :\n"
        "\n"
        "{{ set_password_url }}\n"
        "\n"
        "Ensuite, connecte-toi avec cette adresse e-mail (ou ton nom d'utilisateur, {{ username }}).{% "
        "endif %}\n"
        "\n"
        "Tu ne t'attendais pas à cet e-mail ? Tu peux l'ignorer.\n"
        "\n"
        "L'équipe CoderDojo Belgium",
        "description": "A guardian gave their child their own login (or switched it back on). Sent to the child's "
        "address. Variables: guardian_name, username, uses_link, set_password_url or login_url, "
        "valid_days.",
    },
    {
        "key": "ninja_account_created",
        "language": "nl-be",
        "old_sha256": "041dd057cee5aa71c408c7ac7ba04f93f287f82ba66b762ea3fa43c19792cfaf",
        "subject": "Je eigen CoderDojo-login",
        "body": "Hallo {{ recipient_name }},\n"
        "\n"
        "{{ guardian_name }} heeft een eigen CoderDojo-login voor je gemaakt. Daarmee zie je je\n"
        "gordel, je badges en de sessies waar je naartoe ging, en kan je je zelf inschrijven\n"
        "voor sessies.\n"
        "\n"
        "{% if uses_link %}Je meldt je aan met een link die we je mailen, dus je hoeft geen wachtwoord te "
        "onthouden. Open deze link binnen {{ valid_days }} dagen om je de eerste keer aan te melden:\n"
        "\n"
        "{{ login_url }}\n"
        "\n"
        'Vul de volgende keer dit e-mailadres in op de aanmeldpagina en kies "Aanmelden met een link per '
        'e-mail".{% else %}Kies hier je wachtwoord:\n'
        "\n"
        "{{ set_password_url }}\n"
        "\n"
        "Daarna log je in met dit e-mailadres (of je gebruikersnaam, {{ username }}).{% endif %}\n"
        "\n"
        "Had je deze e-mail niet verwacht? Dan kan je hem negeren.\n"
        "\n"
        "Het CoderDojo Belgium-team",
        "description": "A guardian gave their child their own login (or switched it back on). Sent to the child's "
        "address. Variables: guardian_name, username, uses_link, set_password_url or login_url, "
        "valid_days.",
    },
    {
        "key": "two_step_turned_off",
        "language": "en-us",
        "old_sha256": "f5a2c8c7561fced2bb7dbedb5655a191afe00914cbd6c5e1a18f8cb509992bf1",
        "subject": "Two-step login is off",
        "body": "Hi {{ recipient_name }},\n"
        "\n"
        "{% if by_guardian %}{{ by_guardian }} turned off two-step login for your CoderDojo login.{% elif "
        "by_organisation %}As you asked us, we turned off two-step login for your CoderDojo account.{% "
        "else %}Two-step login was just turned off for your CoderDojo account.{% endif %} Logging in now "
        "only takes your password. Your app, passkeys and backup codes no longer work.\n"
        "\n"
        "You can turn it on again here:\n"
        "\n"
        "{{ security_url }}\n"
        "\n"
        "{% if by_guardian %}Questions about it? Ask {{ by_guardian }}.{% elif by_organisation %}Didn't "
        "you ask for this? Please tell us straight away.{% else %}Wasn't this you? Change your password "
        "straight away and turn it on again.{% endif %}\n"
        "\n"
        "The CoderDojo Belgium team",
        "description": "Two-step login was turned off, by the account holder or by the organisation for someone "
        "who lost their phone (accounts/two_step.py). Variables: by_organisation, by_guardian, "
        "security_url.",
    },
    {
        "key": "two_step_turned_off",
        "language": "fr-be",
        "old_sha256": "14fb022e4505d333d60b6abe1bf1751751277724ddb2514de60eedc86c1c0f03",
        "subject": "La connexion en deux étapes est désactivée",
        "body": "Bonjour {{ recipient_name }},\n"
        "\n"
        "{% if by_guardian %}{{ by_guardian }} a désactivé la connexion en deux étapes de votre connexion "
        "CoderDojo.{% elif by_organisation %}Comme vous nous l'avez demandé, nous avons désactivé la "
        "connexion en deux étapes de votre compte CoderDojo.{% else %}La connexion en deux étapes vient "
        "d'être désactivée sur votre compte CoderDojo.{% endif %} Vous vous connectez maintenant avec "
        "votre seul mot de passe. Votre application, vos clés d'accès et vos codes de secours ne "
        "fonctionnent plus.\n"
        "\n"
        "Vous pouvez la réactiver ici :\n"
        "\n"
        "{{ security_url }}\n"
        "\n"
        "{% if by_guardian %}Des questions ? Posez-les à {{ by_guardian }}.{% elif by_organisation %}Vous "
        "n'avez rien demandé ? Prévenez-nous tout de suite.{% else %}Ce n'était pas vous ? Changez tout de "
        "suite votre mot de passe et réactivez-la.{% endif %}\n"
        "\n"
        "L'équipe CoderDojo Belgium",
        "description": "Two-step login was turned off, by the account holder or by the organisation for someone "
        "who lost their phone (accounts/two_step.py). Variables: by_organisation, by_guardian, "
        "security_url.",
    },
    {
        "key": "two_step_turned_off",
        "language": "nl-be",
        "old_sha256": "a0e5ddc0fdc307a076a63fc53b8021078cc616452236d44af84027c489acf8b7",
        "subject": "Aanmelden in twee stappen staat uit",
        "body": "Hallo {{ recipient_name }},\n"
        "\n"
        "{% if by_guardian %}{{ by_guardian }} zette aanmelden in twee stappen uit voor je "
        "CoderDojo-login.{% elif by_organisation %}Zoals je ons vroeg, hebben we aanmelden in twee stappen "
        "uitgezet voor je CoderDojo-account.{% else %}Aanmelden in twee stappen is net uitgezet voor je "
        "CoderDojo-account.{% endif %} Aanmelden vraagt nu alleen je wachtwoord. Je app, toegangssleutels "
        "en back-upcodes werken niet meer.\n"
        "\n"
        "Je kan het hier weer aanzetten:\n"
        "\n"
        "{{ security_url }}\n"
        "\n"
        "{% if by_guardian %}Vragen? Stel ze aan {{ by_guardian }}.{% elif by_organisation %}Heb je dit "
        "niet gevraagd? Laat het ons dan meteen weten.{% else %}Was jij dit niet? Verander dan meteen je "
        "wachtwoord en zet het weer aan.{% endif %}\n"
        "\n"
        "Het CoderDojo Belgium-team",
        "description": "Two-step login was turned off, by the account holder or by the organisation for someone "
        "who lost their phone (accounts/two_step.py). Variables: by_organisation, by_guardian, "
        "security_url.",
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
    dependencies = [("mailing", "0011_drop_german")]

    operations = [migrations.RunPython(update_templates, migrations.RunPython.noop)]
