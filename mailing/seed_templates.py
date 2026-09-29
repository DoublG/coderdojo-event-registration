"""Example email templates, seeded by `manage.py seed_mailing`.

Each entry is one EmailTemplate key in English, Dutch and French. Bodies
are plain text in Django template syntax, rendered by
mailing.rendering.render(). Dates and times are passed as date/datetime
objects and formatted with |date, so day and month names come out in the
template's language.

Variables every mail gets: `recipient_name`, `site_url`. Mails in a
category people can opt out of also get `unsubscribe_url`.
SAMPLE_CONTEXT has a working example for every key (used by the tests).
"""

from datetime import datetime

from .categories import MailCategory

_SIGNATURE = {
    "en-us": "The CoderDojo Belgium team",
    "nl-be": "Het CoderDojo Belgium-team",
    "fr-be": "L'équipe CoderDojo Belgium",
}

_UNSUBSCRIBE = {
    "en-us": "You get this mail because of your mail preferences. Unsubscribe: {{ unsubscribe_url }}",
    "nl-be": "Je krijgt deze mail door je mailvoorkeuren. Uitschrijven: {{ unsubscribe_url }}",
    "fr-be": "Vous recevez ce mail selon vos préférences. Se désabonner : {{ unsubscribe_url }}",
}


def _body(language, text, unsubscribe=False):
    body = text.strip() + "\n\n" + _SIGNATURE[language]
    if unsubscribe:
        body += "\n\n--\n" + _UNSUBSCRIBE[language]
    return body


TEMPLATES = [
    {
        "key": "registration_confirmed",
        "category": MailCategory.REGISTRATION,
        "description": "After signing a ninja up for a session with a free place. "
        "Variables: ninja_name, event_name, dojo_name, start_time, end_time, venue, event_url, account_url.",
        "subject": {
            "en-us": "{{ ninja_name }} is signed up for {{ event_name }}",
            "nl-be": "{{ ninja_name }} is ingeschreven voor {{ event_name }}",
            "fr-be": "{{ ninja_name }} est inscrit·e à {{ event_name }}",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

{{ ninja_name }} has a place at {{ event_name }} at {{ dojo_name }}.

  When:  {{ start_time|date:"l j F Y" }}, {{ start_time|date:"H:i" }}–{{ end_time|date:"H:i" }}
  Where: {{ venue }}

Bring a charged laptop if you have one. The session details are here:
{{ event_url }}

Can't make it after all? Cancel from your account page, so someone on the
waiting list gets the place: {{ account_url }}
""",
            "nl-be": """
Hallo {{ recipient_name }},

{{ ninja_name }} heeft een plaats voor {{ event_name }} bij {{ dojo_name }}.

  Wanneer: {{ start_time|date:"l j F Y" }}, {{ start_time|date:"H:i" }}–{{ end_time|date:"H:i" }}
  Waar:    {{ venue }}

Breng een opgeladen laptop mee als je er een hebt. Alle details van de sessie:
{{ event_url }}

Toch verhinderd? Schrijf uit via je accountpagina, dan krijgt iemand van de
wachtlijst de plaats: {{ account_url }}
""",
            "fr-be": """
Bonjour {{ recipient_name }},

{{ ninja_name }} a une place pour {{ event_name }} au {{ dojo_name }}.

  Quand : {{ start_time|date:"l j F Y" }}, {{ start_time|date:"H:i" }}–{{ end_time|date:"H:i" }}
  Où :    {{ venue }}

Apportez un ordinateur portable chargé si vous en avez un. Tous les détails de la session :
{{ event_url }}

Un empêchement ? Annulez depuis votre page de compte pour libérer la place
pour quelqu'un de la liste d'attente : {{ account_url }}
""",
        },
    },
    {
        "key": "registration_waitlisted",
        "category": MailCategory.REGISTRATION,
        "description": "After signing a ninja up for a full session: they're on the waiting list. "
        "Variables: ninja_name, event_name, dojo_name, start_time, event_url, account_url.",
        "subject": {
            "en-us": "{{ ninja_name }} is on the waiting list for {{ event_name }}",
            "nl-be": "{{ ninja_name }} staat op de wachtlijst voor {{ event_name }}",
            "fr-be": "{{ ninja_name }} est sur la liste d'attente pour {{ event_name }}",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

{{ event_name }} at {{ dojo_name }} ({{ start_time|date:"l j F" }}) is full, so
{{ ninja_name }} is on the waiting list. If a place comes free, it goes to whoever
has waited longest, and we'll mail you straight away.

Session details: {{ event_url }}
Your registrations: {{ account_url }}
""",
            "nl-be": """
Hallo {{ recipient_name }},

{{ event_name }} bij {{ dojo_name }} ({{ start_time|date:"l j F" }}) is volzet, dus
{{ ninja_name }} staat op de wachtlijst. Komt er een plaats vrij, dan gaat die naar
wie het langst wacht, en mailen we je meteen.

Details van de sessie: {{ event_url }}
Je inschrijvingen: {{ account_url }}
""",
            "fr-be": """
Bonjour {{ recipient_name }},

{{ event_name }} au {{ dojo_name }} ({{ start_time|date:"l j F" }}) est complet :
{{ ninja_name }} est donc sur la liste d'attente. Si une place se libère, elle va à
la personne qui attend depuis le plus longtemps, et nous vous écrivons aussitôt.

Détails de la session : {{ event_url }}
Vos inscriptions : {{ account_url }}
""",
        },
    },
    {
        "key": "waitlist_promoted",
        "category": MailCategory.REGISTRATION,
        "description": "A place came free and a waitlisted ninja moved up. "
        "Variables: ninja_name, event_name, dojo_name, start_time, event_url, account_url.",
        "subject": {
            "en-us": "Good news: {{ ninja_name }} has a place at {{ event_name }}",
            "nl-be": "Goed nieuws: {{ ninja_name }} heeft een plaats voor {{ event_name }}",
            "fr-be": "Bonne nouvelle : {{ ninja_name }} a une place pour {{ event_name }}",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

A place came free at {{ event_name }} at {{ dojo_name }}, and {{ ninja_name }} was
next on the waiting list, so the place is theirs.

The session starts on {{ start_time|date:"l j F" }} at {{ start_time|date:"H:i" }}: {{ event_url }}

If {{ ninja_name }} can't come any more, please cancel on your account page so the
next person gets the place: {{ account_url }}
""",
            "nl-be": """
Hallo {{ recipient_name }},

Er is een plaats vrijgekomen voor {{ event_name }} bij {{ dojo_name }}, en
{{ ninja_name }} stond als eerste op de wachtlijst. De plaats is dus voor jullie.

De sessie begint op {{ start_time|date:"l j F" }} om {{ start_time|date:"H:i" }}: {{ event_url }}

Kan {{ ninja_name }} niet meer komen? Schrijf dan uit via je accountpagina, zodat
de volgende op de lijst de plaats krijgt: {{ account_url }}
""",
            "fr-be": """
Bonjour {{ recipient_name }},

Une place s'est libérée pour {{ event_name }} au {{ dojo_name }}, et {{ ninja_name }}
était en tête de la liste d'attente : la place est pour vous.

La session commence le {{ start_time|date:"l j F" }} à {{ start_time|date:"H:i" }} : {{ event_url }}

Si {{ ninja_name }} ne peut plus venir, annulez depuis votre page de compte pour
que la personne suivante reçoive la place : {{ account_url }}
""",
        },
    },
    {
        "key": "session_reminder",
        "category": MailCategory.REMINDER,
        "description": "Two days before a session, for every confirmed registration. "
        "Variables: ninja_name, event_name, dojo_name, start_time, end_time, venue, event_url, account_url.",
        "subject": {
            "en-us": "Reminder: {{ event_name }} on {{ start_time|date:'l' }}",
            "nl-be": "Herinnering: {{ event_name }} op {{ start_time|date:'l' }}",
            "fr-be": "Rappel : {{ event_name }} ce {{ start_time|date:'l' }}",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

A quick reminder that {{ ninja_name }} is coming to {{ event_name }} at {{ dojo_name }}:

  {{ start_time|date:"l j F" }}, {{ start_time|date:"H:i" }}–{{ end_time|date:"H:i" }}
  {{ venue }}

Details: {{ event_url }}

Plans changed? Cancel on your account page and the place goes to the waiting
list: {{ account_url }}
""",
            "nl-be": """
Hallo {{ recipient_name }},

Een korte herinnering: {{ ninja_name }} komt naar {{ event_name }} bij {{ dojo_name }}.

  {{ start_time|date:"l j F" }}, {{ start_time|date:"H:i" }}–{{ end_time|date:"H:i" }}
  {{ venue }}

Details: {{ event_url }}

Plannen gewijzigd? Schrijf uit via je accountpagina, dan gaat de plaats naar de
wachtlijst: {{ account_url }}
""",
            "fr-be": """
Bonjour {{ recipient_name }},

Petit rappel : {{ ninja_name }} participe à {{ event_name }} au {{ dojo_name }}.

  {{ start_time|date:"l j F" }}, {{ start_time|date:"H:i" }}–{{ end_time|date:"H:i" }}
  {{ venue }}

Détails : {{ event_url }}

Changement de programme ? Annulez depuis votre page de compte et la place ira à
la liste d'attente : {{ account_url }}
""",
        },
        "unsubscribe": True,
    },
    {
        "key": "new_sessions_at_dojo",
        "category": MailCategory.DOJO_NEWS,
        "description": "When a dojo publishes new sessions, to families who attended there. "
        "Variables: dojo_name, dojo_url, events (list of {name, start_time, url}).",
        "subject": {
            "en-us": "New sessions at {{ dojo_name }}",
            "nl-be": "Nieuwe sessies bij {{ dojo_name }}",
            "fr-be": "Nouvelles sessions au {{ dojo_name }}",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

{{ dojo_name }} has published new sessions:
{% for event in events %}
  - {{ event.name }}, {{ event.start_time|date:"l j F, H:i" }}
    {{ event.url }}{% endfor %}

Places go on a first come, first served basis. All sessions at this dojo: {{ dojo_url }}
""",
            "nl-be": """
Hallo {{ recipient_name }},

{{ dojo_name }} heeft nieuwe sessies gepland:
{% for event in events %}
  - {{ event.name }}, {{ event.start_time|date:"l j F, H:i" }}
    {{ event.url }}{% endfor %}

Wie eerst komt, eerst maalt. Alle sessies van deze dojo: {{ dojo_url }}
""",
            "fr-be": """
Bonjour {{ recipient_name }},

Le {{ dojo_name }} a publié de nouvelles sessions :
{% for event in events %}
  - {{ event.name }}, {{ event.start_time|date:"l j F, H:i" }}
    {{ event.url }}{% endfor %}

Les places sont attribuées par ordre d'inscription. Toutes les sessions de ce dojo : {{ dojo_url }}
""",
        },
        "unsubscribe": True,
    },
    {
        "key": "background_check_requested",
        "category": MailCategory.SERVICE,
        "description": "A reviewer asks a volunteer for their criminal record extract (model 2). "
        "Variables: upload_url. Same content as applications.services.request_background_check.",
        "subject": {
            "en-us": "Action needed: background check document",
            "nl-be": "Actie nodig: uittreksel uit het strafregister",
            "fr-be": "Action requise : extrait de casier judiciaire",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

Thanks for volunteering with CoderDojo. Before you can join a dojo's team, Belgian
law requires an extract from the criminal record for anyone working with minors
(model 2, article 596, second paragraph, of the Code of Criminal Procedure).

You can request it for free from your municipality, or online via
mijndossier.rrn.fgov.be. Mention it's for volunteering with minors.

Once you have it, upload it here (or from your account page when logged in):
{{ upload_url }}

We'll let you know once it's been reviewed.
""",
            "nl-be": """
Hallo {{ recipient_name }},

Bedankt dat je vrijwilliger wil worden bij CoderDojo. Voor je bij het team van een
dojo aan de slag kan, vraagt de Belgische wet een uittreksel uit het strafregister
voor iedereen die met minderjarigen werkt (model 2, artikel 596, tweede lid, van
het Wetboek van Strafvordering).

Je vraagt het gratis aan bij je gemeente, of online via mijndossier.rrn.fgov.be.
Vermeld dat het is voor vrijwilligerswerk met minderjarigen.

Heb je het? Laad het hier op (of via je accountpagina als je ingelogd bent):
{{ upload_url }}

We laten je weten wanneer het nagekeken is.
""",
            "fr-be": """
Bonjour {{ recipient_name }},

Merci de vouloir devenir bénévole chez CoderDojo. Avant de rejoindre l'équipe d'un
dojo, la loi belge exige un extrait de casier judiciaire pour toute personne en
contact avec des mineurs (modèle 2, article 596, alinéa 2, du Code d'instruction
criminelle).

Vous pouvez le demander gratuitement à votre commune, ou en ligne via
mondossier.rrn.fgov.be. Précisez qu'il s'agit de bénévolat avec des mineurs.

Une fois reçu, déposez-le ici (ou depuis votre page de compte une fois connecté·e) :
{{ upload_url }}

Nous vous tiendrons au courant après la vérification.
""",
        },
    },
    {
        "key": "background_check_validated",
        "category": MailCategory.SERVICE,
        "description": "A reviewer validated the volunteer's criminal record extract. Variables: expires_at (date).",
        "subject": {
            "en-us": "Your background check has been approved",
            "nl-be": "Je uittreksel uit het strafregister is goedgekeurd",
            "fr-be": "Votre extrait de casier judiciaire a été validé",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

Your background check has been validated. It's valid until {{ expires_at|date:"d/m/Y" }}.
We'll let you know in time when it needs renewing.
""",
            "nl-be": """
Hallo {{ recipient_name }},

Je uittreksel uit het strafregister is goedgekeurd. Het is geldig tot {{ expires_at|date:"d/m/Y" }}.
We laten je tijdig weten wanneer het vernieuwd moet worden.
""",
            "fr-be": """
Bonjour {{ recipient_name }},

Votre extrait de casier judiciaire a été validé. Il est valable jusqu'au {{ expires_at|date:"d/m/Y" }}.
Nous vous préviendrons à temps lorsqu'il faudra le renouveler.
""",
        },
    },
    {
        "key": "background_check_expiring",
        "category": MailCategory.SERVICE,
        "description": "30 days before a volunteer's background check expires (applications.reminders). "
        "Variables: expires_at (date), account_url.",
        "subject": {
            "en-us": 'Your background check expires on {{ expires_at|date:"d/m/Y" }}',
            "nl-be": 'Je uittreksel uit het strafregister vervalt op {{ expires_at|date:"d/m/Y" }}',
            "fr-be": 'Votre extrait de casier judiciaire expire le {{ expires_at|date:"d/m/Y" }}',
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

Your background check is valid until {{ expires_at|date:"d/m/Y" }}. To keep helping at your dojo
without a break, ask your municipality (or mijndossier.rrn.fgov.be) for a new extract from the
criminal record, model 2 (Article 596.2), now: it can take a few days.

From {{ expires_at|date:"d/m/Y" }} you can upload it on your account page:
{{ account_url }}
""",
            "nl-be": """
Hallo {{ recipient_name }},

Je uittreksel uit het strafregister is geldig tot {{ expires_at|date:"d/m/Y" }}. Om zonder onderbreking
te kunnen blijven helpen in je dojo, vraag je nu best een nieuw uittreksel (model 2, artikel 596.2) aan
bij je gemeente of via mijndossier.rrn.fgov.be: dat kan een paar dagen duren.

Vanaf {{ expires_at|date:"d/m/Y" }} kan je het opladen via je accountpagina:
{{ account_url }}
""",
            "fr-be": """
Bonjour {{ recipient_name }},

Votre extrait de casier judiciaire est valable jusqu'au {{ expires_at|date:"d/m/Y" }}. Pour continuer à
aider dans votre dojo sans interruption, demandez dès maintenant un nouvel extrait (modèle 2, article
596.2) à votre commune ou via mijndossier.rrn.fgov.be : cela peut prendre quelques jours.

À partir du {{ expires_at|date:"d/m/Y" }}, vous pourrez le déposer depuis la page de votre compte :
{{ account_url }}
""",
        },
    },
    {
        "key": "background_checks_waiting",
        "category": MailCategory.SERVICE,
        "description": "Daily, to background-check reviewers while uploaded documents wait for a decision "
        "(applications.reminders). Variables: count, oldest (date), checks_url.",
        "subject": {
            "en-us": "Background checks waiting for review ({{ count }})",
            "nl-be": "Uittreksels uit het strafregister om na te kijken ({{ count }})",
            "fr-be": "Extraits de casier judiciaire à vérifier ({{ count }})",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

Uploaded background check documents waiting for your review: {{ count }}, the oldest since
{{ oldest|date:"d/m/Y" }}. Until one is decided, that volunteer can't start at their dojo.

{{ checks_url }}
""",
            "nl-be": """
Hallo {{ recipient_name }},

Opgeladen uittreksels uit het strafregister die op je nazicht wachten: {{ count }}, het oudste sinds
{{ oldest|date:"d/m/Y" }}. Zolang er geen beslissing is, kan die vrijwilliger niet beginnen in de dojo.

{{ checks_url }}
""",
            "fr-be": """
Bonjour {{ recipient_name }},

Extraits de casier judiciaire déposés en attente de votre vérification : {{ count }}, le plus ancien
depuis le {{ oldest|date:"d/m/Y" }}. Tant qu'il n'y a pas de décision, ce bénévole ne peut pas
commencer dans son dojo.

{{ checks_url }}
""",
        },
    },
    {
        "key": "background_check_rejected",
        "category": MailCategory.SERVICE,
        "description": "A reviewer couldn't accept the uploaded document. Variables: account_url.",
        "subject": {
            "en-us": "Your background check document",
            "nl-be": "Je uittreksel uit het strafregister",
            "fr-be": "Votre extrait de casier judiciaire",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

We couldn't accept the document you uploaded for your background check. You can upload
a new one from your account page; get in touch if you're unsure what's needed.

{{ account_url }}
""",
            "nl-be": """
Hallo {{ recipient_name }},

We konden het document dat je voor je uittreksel uit het strafregister opgeladen hebt,
niet aanvaarden. Je kan een nieuw opladen via je accountpagina; neem contact op als je
niet zeker bent wat er nodig is.

{{ account_url }}
""",
            "fr-be": """
Bonjour {{ recipient_name }},

Nous n'avons pas pu accepter le document que vous avez déposé pour votre extrait de casier
judiciaire. Vous pouvez en déposer un nouveau depuis votre page de compte ; contactez-nous
si vous n'êtes pas sûr·e de ce qu'il faut.

{{ account_url }}
""",
        },
    },
    {
        "key": "application_approved",
        "category": MailCategory.SERVICE,
        "description": "A reviewer approved a mentor or champion application. "
        "Variables: kind (mentor | champion), join_dojo_name (the dojo a join request was "
        "sent to, or empty), account_url.",
        "subject": {
            "en-us": "Your CoderDojo application has been approved",
            "nl-be": "Je aanvraag bij CoderDojo is goedgekeurd",
            "fr-be": "Votre candidature chez CoderDojo a été acceptée",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

Your application to become a {% if kind == "champion" %}champion{% else %}mentor{% endif %} has been approved.
{% if kind == "champion" %}You can now create your dojo from your account page.{% elif join_dojo_name %}We've sent your request to join the {{ join_dojo_name }} team; they'll let you know.{% else %}You can now ask to join a dojo's team from its page on the site.{% endif %}

{{ account_url }}
""",
            "nl-be": """
Hallo {{ recipient_name }},

Je aanvraag om {% if kind == "champion" %}champion{% else %}mentor{% endif %} te worden is goedgekeurd.
{% if kind == "champion" %}Je kan nu je dojo aanmaken via je accountpagina.{% elif join_dojo_name %}We hebben je vraag om bij het team van {{ join_dojo_name }} te komen doorgestuurd; zij laten je iets weten.{% else %}Je kan nu vragen om bij het team van een dojo te komen, via de pagina van die dojo.{% endif %}

{{ account_url }}
""",
            "fr-be": """
Bonjour {{ recipient_name }},

Votre candidature pour devenir {% if kind == "champion" %}champion{% else %}mentor{% endif %} a été acceptée.
{% if kind == "champion" %}Vous pouvez maintenant créer votre dojo depuis votre page de compte.{% elif join_dojo_name %}Nous avons transmis votre demande pour rejoindre l'équipe de {{ join_dojo_name }} ; elle vous répondra.{% else %}Vous pouvez maintenant demander à rejoindre l'équipe d'un dojo depuis sa page sur le site.{% endif %}

{{ account_url }}
""",
        },
    },
    {
        "key": "application_rejected",
        "category": MailCategory.SERVICE,
        "description": "A reviewer rejected a mentor or champion application. No extra variables.",
        "subject": {
            "en-us": "Your CoderDojo application",
            "nl-be": "Je aanvraag bij CoderDojo",
            "fr-be": "Votre candidature chez CoderDojo",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

Thank you for applying. Unfortunately we can't approve your application at this time;
get in touch if you'd like to know more.
""",
            "nl-be": """
Hallo {{ recipient_name }},

Bedankt voor je aanvraag. Helaas kunnen we ze op dit moment niet goedkeuren; neem
contact op als je meer wil weten.
""",
            "fr-be": """
Bonjour {{ recipient_name }},

Merci pour votre candidature. Malheureusement, nous ne pouvons pas l'accepter pour le
moment ; contactez-nous si vous souhaitez en savoir plus.
""",
        },
    },
    {
        "key": "password_reset",
        "category": MailCategory.SERVICE,
        "description": "Someone asked to reset the account's password. Variables: reset_url.",
        "subject": {
            "en-us": "Reset your CoderDojo password",
            "nl-be": "Stel je CoderDojo-wachtwoord opnieuw in",
            "fr-be": "Réinitialisez votre mot de passe CoderDojo",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

Someone (hopefully you) asked to reset the password on your CoderDojo account.

Set a new password here:

{{ reset_url }}

If you didn't ask for this, you can ignore this email: your password won't change.
""",
            "nl-be": """
Hallo {{ recipient_name }},

Iemand (hopelijk jij) vroeg om het wachtwoord van je CoderDojo-account opnieuw in te
stellen.

Kies hier een nieuw wachtwoord:

{{ reset_url }}

Heb je dit niet gevraagd? Dan kan je deze e-mail negeren: je wachtwoord blijft hetzelfde.
""",
            "fr-be": """
Bonjour {{ recipient_name }},

Quelqu'un (vous, espérons-le) a demandé à réinitialiser le mot de passe de votre compte
CoderDojo.

Choisissez un nouveau mot de passe ici :

{{ reset_url }}

Si vous n'avez rien demandé, vous pouvez ignorer cet e-mail : votre mot de passe ne change pas.
""",
        },
    },
    {
        "key": "email_change_confirm",
        "category": MailCategory.SERVICE,
        "description": "Sent to the NEW address when someone asks to change the account's email "
        "(accounts/email_change.py). Variables: new_email, old_email, confirm_url, valid_hours, "
        "by_organisation, by_guardian (a guardian's name, for a child's login).",
        "subject": {
            "en-us": "Confirm your new email address",
            "nl-be": "Bevestig je nieuwe e-mailadres",
            "fr-be": "Confirmez votre nouvelle adresse e-mail",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

{% if by_guardian %}{{ by_guardian }} is changing the email address of your CoderDojo login from {{ old_email }} to {{ new_email }}.{% elif by_organisation %}At your request, CoderDojo Belgium is changing the email address of your CoderDojo account from {{ old_email }} to {{ new_email }}.{% else %}You asked to change the email address of your CoderDojo account from {{ old_email }} to {{ new_email }}.{% endif %}

To confirm, open this link within {{ valid_hours }} hours:

{{ confirm_url }}

Nothing changes until you do. If you didn't ask for this, you can ignore this email.
""",
            "nl-be": """
Hallo {{ recipient_name }},

{% if by_guardian %}{{ by_guardian }} wijzigt het e-mailadres van je CoderDojo-login van {{ old_email }} naar {{ new_email }}.{% elif by_organisation %}Op jouw vraag wijzigt CoderDojo Belgium het e-mailadres van je CoderDojo-account van {{ old_email }} naar {{ new_email }}.{% else %}Je vroeg om het e-mailadres van je CoderDojo-account te wijzigen van {{ old_email }} naar {{ new_email }}.{% endif %}

Open deze link binnen {{ valid_hours }} uur om het te bevestigen:

{{ confirm_url }}

Tot dan verandert er niets. Heb je dit niet gevraagd? Dan kan je deze e-mail negeren.
""",
            "fr-be": """
Bonjour {{ recipient_name }},

{% if by_guardian %}{{ by_guardian }} change l'adresse e-mail de votre connexion CoderDojo : {{ old_email }} devient {{ new_email }}.{% elif by_organisation %}À votre demande, CoderDojo Belgium change l'adresse e-mail de votre compte CoderDojo : {{ old_email }} devient {{ new_email }}.{% else %}Vous avez demandé à changer l'adresse e-mail de votre compte CoderDojo : {{ old_email }} devient {{ new_email }}.{% endif %}

Pour confirmer, ouvrez ce lien dans les {{ valid_hours }} heures :

{{ confirm_url }}

Rien ne change avant cela. Si vous n'avez rien demandé, vous pouvez ignorer cet e-mail.
""",
        },
    },
    {
        "key": "email_changed",
        "category": MailCategory.SERVICE,
        "description": "Sent to the OLD address once the account's email has changed "
        "(accounts/email_change.py). Variables: new_email, changed_at, contact_url.",
        "subject": {
            "en-us": "Your CoderDojo email address was changed",
            "nl-be": "Het e-mailadres van je CoderDojo-account is gewijzigd",
            "fr-be": "L'adresse e-mail de votre compte CoderDojo a changé",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

On {{ changed_at|date:"j F Y" }} at {{ changed_at|date:"H:i" }}, the email address of your CoderDojo account was changed to {{ new_email }}. From now on, we send your mail there and you log in with it. This address won't get our mails any more.

Wasn't this you? Contact us straight away:

{{ contact_url }}
""",
            "nl-be": """
Hallo {{ recipient_name }},

Op {{ changed_at|date:"j F Y" }} om {{ changed_at|date:"H:i" }} is het e-mailadres van je CoderDojo-account gewijzigd naar {{ new_email }}. Voortaan sturen we je mails daarheen en meld je je daarmee aan. Dit adres krijgt geen mails van ons meer.

Was jij dit niet? Neem dan meteen contact met ons op:

{{ contact_url }}
""",
            "fr-be": """
Bonjour {{ recipient_name }},

Le {{ changed_at|date:"j F Y" }} à {{ changed_at|date:"H:i" }}, l'adresse e-mail de votre compte CoderDojo a été remplacée par {{ new_email }}. Désormais, nous vous écrivons à cette adresse et vous vous connectez avec elle. Cette adresse-ci ne recevra plus nos e-mails.

Ce n'était pas vous ? Contactez-nous immédiatement :

{{ contact_url }}
""",
        },
    },
    {
        "key": "login_link",
        "category": MailCategory.SERVICE,
        "description": "A login link for an account that logs in with one (accounts/login_links.py). Variables: "
        "login_url, first (the first one, after sign-up), valid_minutes, valid_days (for the first one).",
        "subject": {
            "en-us": "{% if first %}Welcome: log in to CoderDojo{% else %}Your CoderDojo login link{% endif %}",
            "nl-be": "{% if first %}Welkom: meld je aan bij CoderDojo{% else %}Je inloglink voor CoderDojo{% endif %}",
            "fr-be": "{% if first %}Bienvenue : connectez-vous à CoderDojo{% else %}Votre lien de connexion CoderDojo{% endif %}",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

{% if first %}Your CoderDojo account is ready. You log in with a link we mail you, so there's no password to remember. Open this link within {{ valid_days }} days to log in for the first time:{% else %}Here's your link to log in to CoderDojo. It works once, within {{ valid_minutes }} minutes:{% endif %}

{{ login_url }}

The link logs in the device you open it on. Next time, ask for a new link on the login page.

Didn't ask for this? Then you can ignore this email: nobody can log in without it.
""",
            "nl-be": """
Hallo {{ recipient_name }},

{% if first %}Je CoderDojo-account is klaar. Je meldt je aan met een link die we je mailen, dus je hoeft geen wachtwoord te onthouden. Open deze link binnen {{ valid_days }} dagen om je de eerste keer aan te melden:{% else %}Hier is je link om je aan te melden bij CoderDojo. Hij werkt één keer, binnen {{ valid_minutes }} minuten:{% endif %}

{{ login_url }}

De link meldt je aan op het toestel waarop je hem opent. Vraag de volgende keer een nieuwe link aan op de aanmeldpagina.

Heb je dit niet gevraagd? Dan kan je deze e-mail negeren: zonder deze mail kan niemand zich aanmelden.
""",
            "fr-be": """
Bonjour {{ recipient_name }},

{% if first %}Votre compte CoderDojo est prêt. Vous vous connectez avec un lien que nous vous envoyons par e-mail : pas de mot de passe à retenir. Ouvrez ce lien dans les {{ valid_days }} jours pour vous connecter la première fois :{% else %}Voici votre lien pour vous connecter à CoderDojo. Il fonctionne une fois, dans les {{ valid_minutes }} minutes :{% endif %}

{{ login_url }}

Le lien connecte l'appareil sur lequel vous l'ouvrez. La prochaine fois, demandez un nouveau lien sur la page de connexion.

Vous n'avez rien demandé ? Vous pouvez ignorer cet e-mail : personne ne peut se connecter sans lui.
""",
        },
    },
    {
        "key": "login_link_not_available",
        "category": MailCategory.SERVICE,
        "description": "Someone asked for a login link for an account that logs in with a password "
        "(accounts/login_links.py). Variables: reset_url, security_url.",
        "subject": {
            "en-us": "You asked for a CoderDojo login link",
            "nl-be": "Je vroeg een inloglink voor CoderDojo",
            "fr-be": "Vous avez demandé un lien de connexion CoderDojo",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

Someone (hopefully you) asked for a login link for your CoderDojo account. Your account logs in with a password, so we didn't send one.

Forgot your password? Choose a new one here:

{{ reset_url }}

Would you rather log in with a link each time? Once you're logged in, you can switch on your Sign-in security page:

{{ security_url }}

Didn't ask for this? Then you can ignore this email: nothing has changed.
""",
            "nl-be": """
Hallo {{ recipient_name }},

Iemand (hopelijk jij) vroeg een inloglink voor je CoderDojo-account. Je account meldt zich aan met een wachtwoord, dus we stuurden er geen.

Wachtwoord vergeten? Kies hier een nieuw:

{{ reset_url }}

Meld je je liever telkens aan met een link? Eens je aangemeld bent, kan je dat wijzigen op je pagina Aanmeldbeveiliging:

{{ security_url }}

Heb je dit niet gevraagd? Dan kan je deze e-mail negeren: er is niets veranderd.
""",
            "fr-be": """
Bonjour {{ recipient_name }},

Quelqu'un (vous, espérons-le) a demandé un lien de connexion pour votre compte CoderDojo. Votre compte se connecte avec un mot de passe : nous n'en avons donc pas envoyé.

Mot de passe oublié ? Choisissez-en un nouveau ici :

{{ reset_url }}

Vous préférez vous connecter chaque fois avec un lien ? Une fois connecté, vous pouvez changer cela sur votre page Sécurité de connexion :

{{ security_url }}

Vous n'avez rien demandé ? Vous pouvez ignorer cet e-mail : rien n'a changé.
""",
        },
    },
    {
        "key": "login_method_confirm",
        "category": MailCategory.SERVICE,
        "description": "Confirms a switch to logging in with a link, from the account's mailbox "
        "(accounts/login_links.py). Variables: confirm_url, valid_hours.",
        "subject": {
            "en-us": "Confirm: log in to CoderDojo with a link",
            "nl-be": "Bevestig: aanmelden bij CoderDojo met een link",
            "fr-be": "Confirmez : se connecter à CoderDojo avec un lien",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

You asked to log in to your CoderDojo account with a link we mail you, instead of a password. To confirm, open this link within {{ valid_hours }} hours:

{{ confirm_url }}

Then your password stops working, and you're logged out on your other devices. Nothing changes until you confirm. If you didn't ask for this, you can ignore this email.
""",
            "nl-be": """
Hallo {{ recipient_name }},

Je vroeg om je bij je CoderDojo-account aan te melden met een link die we je mailen, in plaats van met een wachtwoord. Open deze link binnen {{ valid_hours }} uur om het te bevestigen:

{{ confirm_url }}

Daarna werkt je wachtwoord niet meer en word je afgemeld op je andere toestellen. Tot je bevestigt, verandert er niets. Heb je dit niet gevraagd? Dan kan je deze e-mail negeren.
""",
            "fr-be": """
Bonjour {{ recipient_name }},

Vous avez demandé à vous connecter à votre compte CoderDojo avec un lien envoyé par e-mail, au lieu d'un mot de passe. Pour confirmer, ouvrez ce lien dans les {{ valid_hours }} heures :

{{ confirm_url }}

Ensuite, votre mot de passe ne fonctionne plus et vous êtes déconnecté sur vos autres appareils. Rien ne change avant votre confirmation. Si vous n'avez rien demandé, vous pouvez ignorer cet e-mail.
""",
        },
    },
    {
        "key": "login_method_changed",
        "category": MailCategory.SERVICE,
        "description": "The account's way of logging in changed (accounts/login_links.py). Variables: method "
        "(link or password), by_guardian (the guardian's name when they switched a child's login back to a "
        "password), security_url, contact_url.",
        "subject": {
            "en-us": "How you log in to CoderDojo changed",
            "nl-be": "Hoe je je aanmeldt bij CoderDojo is gewijzigd",
            "fr-be": "Votre façon de vous connecter à CoderDojo a changé",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

{% if method == "link" %}From now on you log in to CoderDojo with a link we mail you. Your password no longer works.{% elif by_guardian %}{{ by_guardian }} switched your CoderDojo login back to a password. We've sent you a separate mail to choose one.{% else %}From now on you log in to CoderDojo with your new password. Login links no longer work.{% endif %}

You can see and change it on your Sign-in security page:

{{ security_url }}

Wasn't this you? Contact us straight away:

{{ contact_url }}
""",
            "nl-be": """
Hallo {{ recipient_name }},

{% if method == "link" %}Voortaan meld je je bij CoderDojo aan met een link die we je mailen. Je wachtwoord werkt niet meer.{% elif by_guardian %}{{ by_guardian }} zette je CoderDojo-login terug op een wachtwoord. We stuurden je een aparte mail om er een te kiezen.{% else %}Voortaan meld je je bij CoderDojo aan met je nieuwe wachtwoord. Inloglinks werken niet meer.{% endif %}

Je kan het bekijken en wijzigen op je pagina Aanmeldbeveiliging:

{{ security_url }}

Was jij dit niet? Neem dan meteen contact met ons op:

{{ contact_url }}
""",
            "fr-be": """
Bonjour {{ recipient_name }},

{% if method == "link" %}Désormais, vous vous connectez à CoderDojo avec un lien que nous vous envoyons par e-mail. Votre mot de passe ne fonctionne plus.{% elif by_guardian %}{{ by_guardian }} a remis votre connexion CoderDojo sur un mot de passe. Nous vous avons envoyé un autre e-mail pour en choisir un.{% else %}Désormais, vous vous connectez à CoderDojo avec votre nouveau mot de passe. Les liens de connexion ne fonctionnent plus.{% endif %}

Vous pouvez le voir et le changer sur votre page Sécurité de connexion :

{{ security_url }}

Ce n'était pas vous ? Contactez-nous immédiatement :

{{ contact_url }}
""",
        },
    },
    {
        "key": "child_login_changed",
        "category": MailCategory.SERVICE,
        "description": "To a child's guardians when the child's own login changed (accounts/security_mail.py). "
        "Variables: child_name, child_url, change (what changed: see security_mail), method, new_email.",
        "subject": {
            "en-us": "{{ child_name }}'s CoderDojo login changed",
            "nl-be": "De CoderDojo-login van {{ child_name }} is gewijzigd",
            "fr-be": "La connexion CoderDojo de {{ child_name }} a changé",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

{% if change == "two_step_turned_on" %}{{ child_name }} turned on two-step login.{% elif change == "two_step_method_added" %}{{ child_name }} added a sign-in method for two-step login.{% elif change == "two_step_method_removed" %}{{ child_name }} removed a sign-in method for two-step login.{% elif change == "two_step_turned_off" %}Two-step login was turned off for {{ child_name }}'s login.{% elif change == "backup_code_used" %}{{ child_name }} logged in with a backup code.{% elif change == "login_method_changed" %}{% if method == "link" %}{{ child_name }} now logs in with a link we mail them.{% else %}{{ child_name }} now logs in with a password.{% endif %}{% elif change == "email_changed" %}{{ child_name }}'s login now uses the address {{ new_email }}.{% endif %}

You manage {{ child_name }}'s login on their page:

{{ child_url }}

Anything you don't recognise? Have a look together, or contact us.
""",
            "nl-be": """
Hallo {{ recipient_name }},

{% if change == "two_step_turned_on" %}{{ child_name }} zette aanmelden in twee stappen aan.{% elif change == "two_step_method_added" %}{{ child_name }} voegde een aanmeldmethode toe voor aanmelden in twee stappen.{% elif change == "two_step_method_removed" %}{{ child_name }} verwijderde een aanmeldmethode voor aanmelden in twee stappen.{% elif change == "two_step_turned_off" %}Aanmelden in twee stappen is uitgezet voor de login van {{ child_name }}.{% elif change == "backup_code_used" %}{{ child_name }} meldde zich aan met een back-upcode.{% elif change == "login_method_changed" %}{% if method == "link" %}{{ child_name }} meldt zich nu aan met een link die we mailen.{% else %}{{ child_name }} meldt zich nu aan met een wachtwoord.{% endif %}{% elif change == "email_changed" %}De login van {{ child_name }} gebruikt nu het adres {{ new_email }}.{% endif %}

Je beheert de login van {{ child_name }} op diens pagina:

{{ child_url }}

Iets wat je niet herkent? Bekijk het samen, of neem contact met ons op.
""",
            "fr-be": """
Bonjour {{ recipient_name }},

{% if change == "two_step_turned_on" %}{{ child_name }} a activé la connexion en deux étapes.{% elif change == "two_step_method_added" %}{{ child_name }} a ajouté une méthode de connexion en deux étapes.{% elif change == "two_step_method_removed" %}{{ child_name }} a supprimé une méthode de connexion en deux étapes.{% elif change == "two_step_turned_off" %}La connexion en deux étapes a été désactivée pour la connexion de {{ child_name }}.{% elif change == "backup_code_used" %}{{ child_name }} s'est connecté avec un code de secours.{% elif change == "login_method_changed" %}{% if method == "link" %}{{ child_name }} se connecte maintenant avec un lien envoyé par e-mail.{% else %}{{ child_name }} se connecte maintenant avec un mot de passe.{% endif %}{% elif change == "email_changed" %}La connexion de {{ child_name }} utilise maintenant l'adresse {{ new_email }}.{% endif %}

Vous gérez la connexion de {{ child_name }} sur sa page :

{{ child_url }}

Quelque chose que vous ne reconnaissez pas ? Regardez-le ensemble, ou contactez-nous.
""",
        },
    },
    {
        "key": "organisation_role_changed",
        "category": MailCategory.SERVICE,
        "description": "An organisation admin gave or took away the account's organisation roles "
        "(accounts/organisation_people.py). Variables: roles (the keys it now holds: admin, reviewer, "
        "board; empty = none left), changed_by, manage_url, contact_url.",
        "subject": {
            "en-us": "Your role in the CoderDojo Belgium organisation",
            "nl-be": "Je rol in de organisatie van CoderDojo Belgium",
            "fr-be": "Votre rôle dans l'organisation de CoderDojo Belgium",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

{% if roles %}{{ changed_by }} changed your roles in the CoderDojo Belgium organisation. You now have:
{% for role in roles %}
- {% if role == "admin" %}Admin: the organisation dashboard (campaigns, content, awards, privacy, sign-in security and people){% elif role == "reviewer" %}Background-check reviewer: background checks and applications{% else %}Board: read-only oversight{% endif %}{% endfor %}

You find it under Manage, where you can also ask for the Django admin when you need it (12 hours at a time):

{{ manage_url }}{% else %}{{ changed_by }} took away your roles in the CoderDojo Belgium organisation. Your account stays as it was.{% endif %}

Questions? Contact us:

{{ contact_url }}
""",
            "nl-be": """
Hallo {{ recipient_name }},

{% if roles %}{{ changed_by }} heeft je rollen in de organisatie van CoderDojo Belgium gewijzigd. Je hebt nu:
{% for role in roles %}
- {% if role == "admin" %}Beheerder: het organisatiedashboard (campagnes, inhoud, onderscheidingen, privacy, aanmeldbeveiliging en mensen){% elif role == "reviewer" %}Beoordelaar van uittreksels: uittreksels uit het strafregister en aanvragen{% else %}Bestuur: toezicht, alleen lezen{% endif %}{% endfor %}

Je vindt het onder Beheren, waar je ook toegang tot de Django-admin kunt vragen als je die nodig hebt (telkens 12 uur):

{{ manage_url }}{% else %}{{ changed_by }} heeft je rollen in de organisatie van CoderDojo Belgium weggenomen. Je account blijft zoals het was.{% endif %}

Vragen? Neem contact met ons op:

{{ contact_url }}
""",
            "fr-be": """
Bonjour {{ recipient_name }},

{% if roles %}{{ changed_by }} a modifié vos rôles dans l'organisation de CoderDojo Belgium. Vous avez maintenant :
{% for role in roles %}
- {% if role == "admin" %}Administrateur : le tableau de bord de l'organisation (campagnes, contenu, distinctions, vie privée, sécurité de connexion et personnes){% elif role == "reviewer" %}Évaluateur des extraits de casier : extraits de casier judiciaire et candidatures{% else %}Conseil d'administration : supervision, en lecture seule{% endif %}{% endfor %}

Vous le trouvez sous Gérer, où vous pouvez aussi demander l'accès à l'admin Django quand vous en avez besoin (12 heures à la fois) :

{{ manage_url }}{% else %}{{ changed_by }} vous a retiré vos rôles dans l'organisation de CoderDojo Belgium. Votre compte reste tel quel.{% endif %}

Des questions ? Contactez-nous :

{{ contact_url }}
""",
        },
    },
    {
        "key": "organisation_invitation",
        "category": MailCategory.SERVICE,
        "description": "An invitation to someone without an account to take organisation roles "
        "(accounts/invitations.py; sent to the address, no account yet). Variables: invited_by, roles "
        "(admin, reviewer, board), accept_url, valid_days.",
        "subject": {
            "en-us": "You're invited to the CoderDojo Belgium organisation",
            "nl-be": "Je bent uitgenodigd in de organisatie van CoderDojo Belgium",
            "fr-be": "Vous êtes invité·e dans l'organisation de CoderDojo Belgium",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

{{ invited_by }} invites you to CoderDojo Belgium's organisation team, with these roles:
{% for role in roles %}
- {% if role == "admin" %}Admin: the organisation dashboard (campaigns, content, awards, privacy, sign-in security and people){% elif role == "reviewer" %}Background-check reviewer: background checks and applications{% else %}Board: read-only oversight{% endif %}{% endfor %}

Create your account (or log in, if you have one with this address) and accept here:

{{ accept_url }}

The link works for {{ valid_days }} days. Didn't expect this? You can ignore this email.
""",
            "nl-be": """
Hallo {{ recipient_name }},

{{ invited_by }} nodigt je uit in het organisatieteam van CoderDojo Belgium, met deze rollen:
{% for role in roles %}
- {% if role == "admin" %}Beheerder: het organisatiedashboard (campagnes, inhoud, onderscheidingen, privacy, aanmeldbeveiliging en mensen){% elif role == "reviewer" %}Beoordelaar van uittreksels: uittreksels uit het strafregister en aanvragen{% else %}Bestuur: toezicht, alleen lezen{% endif %}{% endfor %}

Maak je account aan (of meld je aan, als je er al een hebt met dit adres) en aanvaard hier:

{{ accept_url }}

De link werkt {{ valid_days }} dagen. Verwachtte je dit niet? Dan mag je deze e-mail negeren.
""",
            "fr-be": """
Bonjour {{ recipient_name }},

{{ invited_by }} vous invite dans l'équipe de l'organisation de CoderDojo Belgium, avec ces rôles :
{% for role in roles %}
- {% if role == "admin" %}Administrateur : le tableau de bord de l'organisation (campagnes, contenu, distinctions, vie privée, sécurité de connexion et personnes){% elif role == "reviewer" %}Évaluateur des extraits de casier : extraits de casier judiciaire et candidatures{% else %}Conseil d'administration : supervision, en lecture seule{% endif %}{% endfor %}

Créez votre compte (ou connectez-vous, si vous en avez déjà un avec cette adresse) et acceptez ici :

{{ accept_url }}

Le lien est valable {{ valid_days }} jours. Vous ne vous y attendiez pas ? Vous pouvez ignorer cet e-mail.
""",
        },
    },
    {
        "key": "two_step_turned_on",
        "category": MailCategory.SERVICE,
        "description": "Two-step login was turned on for the account (accounts/two_step.py). "
        "Variables: method (app or passkey), security_url.",
        "subject": {
            "en-us": "Two-step login is on",
            "nl-be": "Aanmelden in twee stappen staat aan",
            "fr-be": "La connexion en deux étapes est activée",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

Two-step login is now on for your CoderDojo account. From now on, logging in takes your password and {% if method == "passkey" %}your passkey{% else %}a code from your authenticator app{% endif %}.

Keep your backup codes somewhere safe: they get you in if you lose your phone or passkey.

Wasn't this you? Change your password straight away and check your sign-in methods:

{{ security_url }}
""",
            "nl-be": """
Hallo {{ recipient_name }},

Aanmelden in twee stappen staat nu aan voor je CoderDojo-account. Voortaan meld je je aan met je wachtwoord en {% if method == "passkey" %}je toegangssleutel{% else %}een code uit je authenticator-app{% endif %}.

Bewaar je back-upcodes op een veilige plek: daarmee kom je binnen als je je telefoon of toegangssleutel kwijt bent.

Was jij dit niet? Verander dan meteen je wachtwoord en kijk je aanmeldmethoden na:

{{ security_url }}
""",
            "fr-be": """
Bonjour {{ recipient_name }},

La connexion en deux étapes est maintenant activée sur votre compte CoderDojo. Désormais, vous vous connectez avec votre mot de passe et {% if method == "passkey" %}votre clé d'accès{% else %}un code de votre application d'authentification{% endif %}.

Gardez vos codes de secours en lieu sûr : ils vous permettent de vous connecter si vous perdez votre téléphone ou votre clé d'accès.

Ce n'était pas vous ? Changez tout de suite votre mot de passe et vérifiez vos méthodes de connexion :

{{ security_url }}
""",
        },
    },
    {
        "key": "two_step_method_added",
        "category": MailCategory.SERVICE,
        "description": "A sign-in method was added to an account that already had two-step login "
        "(accounts/two_step.py). Variables: method (app or passkey), security_url.",
        "subject": {
            "en-us": "A new sign-in method on your account",
            "nl-be": "Een nieuwe aanmeldmethode op je account",
            "fr-be": "Une nouvelle méthode de connexion sur votre compte",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

{% if method == "passkey" %}A passkey{% else %}An authenticator app{% endif %} was just added to your CoderDojo account for two-step login.

Wasn't this you? Remove it and change your password straight away:

{{ security_url }}
""",
            "nl-be": """
Hallo {{ recipient_name }},

Er is net {% if method == "passkey" %}een toegangssleutel{% else %}een authenticator-app{% endif %} toegevoegd aan je CoderDojo-account om in twee stappen aan te melden.

Was jij dit niet? Verwijder die dan en verander meteen je wachtwoord:

{{ security_url }}
""",
            "fr-be": """
Bonjour {{ recipient_name }},

{% if method == "passkey" %}Une clé d'accès vient d'être ajoutée{% else %}Une application d'authentification vient d'être ajoutée{% endif %} à votre compte CoderDojo pour la connexion en deux étapes.

Ce n'était pas vous ? Supprimez-la et changez tout de suite votre mot de passe :

{{ security_url }}
""",
        },
    },
    {
        "key": "two_step_method_removed",
        "category": MailCategory.SERVICE,
        "description": "A sign-in method was removed; two-step login stays on with the others "
        "(accounts/two_step.py). Variables: method (app or passkey), security_url.",
        "subject": {
            "en-us": "A sign-in method was removed from your account",
            "nl-be": "Er is een aanmeldmethode van je account verwijderd",
            "fr-be": "Une méthode de connexion a été retirée de votre compte",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

{% if method == "passkey" %}A passkey{% else %}Your authenticator app{% endif %} was just removed from your CoderDojo account. Two-step login stays on with your other sign-in methods.

Wasn't this you? Change your password straight away and check your sign-in methods:

{{ security_url }}
""",
            "nl-be": """
Hallo {{ recipient_name }},

Er is net {% if method == "passkey" %}een toegangssleutel{% else %}je authenticator-app{% endif %} van je CoderDojo-account verwijderd. Aanmelden in twee stappen blijft aan met je andere aanmeldmethoden.

Was jij dit niet? Verander dan meteen je wachtwoord en kijk je aanmeldmethoden na:

{{ security_url }}
""",
            "fr-be": """
Bonjour {{ recipient_name }},

{% if method == "passkey" %}Une clé d'accès vient d'être retirée{% else %}Votre application d'authentification vient d'être retirée{% endif %} de votre compte CoderDojo. La connexion en deux étapes reste activée avec vos autres méthodes de connexion.

Ce n'était pas vous ? Changez tout de suite votre mot de passe et vérifiez vos méthodes de connexion :

{{ security_url }}
""",
        },
    },
    {
        "key": "two_step_turned_off",
        "category": MailCategory.SERVICE,
        "description": "Two-step login was turned off, by the account holder or by the organisation for someone "
        "who lost their phone (accounts/two_step.py). Variables: by_organisation, by_guardian, security_url.",
        "subject": {
            "en-us": "Two-step login is off",
            "nl-be": "Aanmelden in twee stappen staat uit",
            "fr-be": "La connexion en deux étapes est désactivée",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

{% if by_guardian %}{{ by_guardian }} turned off two-step login for your CoderDojo login.{% elif by_organisation %}As you asked us, we turned off two-step login for your CoderDojo account.{% else %}Two-step login was just turned off for your CoderDojo account.{% endif %} Logging in now only takes your password. Your app, passkeys and backup codes no longer work.

You can turn it on again here:

{{ security_url }}

{% if by_guardian %}Questions about it? Ask {{ by_guardian }}.{% elif by_organisation %}Didn't you ask for this? Please tell us straight away.{% else %}Wasn't this you? Change your password straight away and turn it on again.{% endif %}
""",
            "nl-be": """
Hallo {{ recipient_name }},

{% if by_guardian %}{{ by_guardian }} zette aanmelden in twee stappen uit voor je CoderDojo-login.{% elif by_organisation %}Zoals je ons vroeg, hebben we aanmelden in twee stappen uitgezet voor je CoderDojo-account.{% else %}Aanmelden in twee stappen is net uitgezet voor je CoderDojo-account.{% endif %} Aanmelden vraagt nu alleen je wachtwoord. Je app, toegangssleutels en back-upcodes werken niet meer.

Je kan het hier weer aanzetten:

{{ security_url }}

{% if by_guardian %}Vragen? Stel ze aan {{ by_guardian }}.{% elif by_organisation %}Heb je dit niet gevraagd? Laat het ons dan meteen weten.{% else %}Was jij dit niet? Verander dan meteen je wachtwoord en zet het weer aan.{% endif %}
""",
            "fr-be": """
Bonjour {{ recipient_name }},

{% if by_guardian %}{{ by_guardian }} a désactivé la connexion en deux étapes de votre connexion CoderDojo.{% elif by_organisation %}Comme vous nous l'avez demandé, nous avons désactivé la connexion en deux étapes de votre compte CoderDojo.{% else %}La connexion en deux étapes vient d'être désactivée sur votre compte CoderDojo.{% endif %} Vous vous connectez maintenant avec votre seul mot de passe. Votre application, vos clés d'accès et vos codes de secours ne fonctionnent plus.

Vous pouvez la réactiver ici :

{{ security_url }}

{% if by_guardian %}Des questions ? Posez-les à {{ by_guardian }}.{% elif by_organisation %}Vous n'avez rien demandé ? Prévenez-nous tout de suite.{% else %}Ce n'était pas vous ? Changez tout de suite votre mot de passe et réactivez-la.{% endif %}
""",
        },
    },
    {
        "key": "backup_code_used",
        "category": MailCategory.SERVICE,
        "description": "Someone logged in with one of the account's backup codes (accounts/two_step.py). "
        "Variables: codes_left, security_url.",
        "subject": {
            "en-us": "A backup code was used to log in",
            "nl-be": "Er is aangemeld met een back-upcode",
            "fr-be": "Un code de secours a servi à se connecter",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

Someone just logged in to your CoderDojo account with one of your backup codes. You have {{ codes_left }} left.

Lost your phone or passkey? Set up a new one, and make new backup codes, here:

{{ security_url }}

Wasn't this you? Change your password straight away and make new backup codes.
""",
            "nl-be": """
Hallo {{ recipient_name }},

Er is net aangemeld op je CoderDojo-account met een van je back-upcodes. Je hebt er nog {{ codes_left }}.

Ben je je telefoon of toegangssleutel kwijt? Stel dan hier een nieuwe in, en maak nieuwe back-upcodes:

{{ security_url }}

Was jij dit niet? Verander dan meteen je wachtwoord en maak nieuwe back-upcodes.
""",
            "fr-be": """
Bonjour {{ recipient_name }},

Quelqu'un vient de se connecter à votre compte CoderDojo avec un de vos codes de secours. Il vous en reste {{ codes_left }}.

Vous avez perdu votre téléphone ou votre clé d'accès ? Configurez-en un nouveau, et créez de nouveaux codes de secours, ici :

{{ security_url }}

Ce n'était pas vous ? Changez tout de suite votre mot de passe et créez de nouveaux codes de secours.
""",
        },
    },
    {
        "key": "ninja_account_created",
        "category": MailCategory.SERVICE,
        "description": "A guardian gave their child their own login (or switched it back on). Sent to the "
        "child's address. Variables: guardian_name, username, uses_link, set_password_url or login_url, valid_days.",
        "subject": {
            "en-us": "Your own CoderDojo login",
            "nl-be": "Je eigen CoderDojo-login",
            "fr-be": "Ton propre compte CoderDojo",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

{{ guardian_name }} made you your own CoderDojo login. With it you can see your belt,
your badges and the sessions you've been to, and sign yourself up for sessions.

{% if uses_link %}You log in with a link we mail you, so there's no password to remember. Open this link within {{ valid_days }} days to log in for the first time:

{{ login_url }}

Next time, enter this email address on the login page and choose "Log in with an emailed link".{% else %}Choose your password here:

{{ set_password_url }}

After that, log in with this email address (or your username, {{ username }}).{% endif %}

Didn't expect this mail? Then you can ignore it.
""",
            "nl-be": """
Hallo {{ recipient_name }},

{{ guardian_name }} heeft een eigen CoderDojo-login voor je gemaakt. Daarmee zie je je
gordel, je badges en de sessies waar je naartoe ging, en kan je je zelf inschrijven
voor sessies.

{% if uses_link %}Je meldt je aan met een link die we je mailen, dus je hoeft geen wachtwoord te onthouden. Open deze link binnen {{ valid_days }} dagen om je de eerste keer aan te melden:

{{ login_url }}

Vul de volgende keer dit e-mailadres in op de aanmeldpagina en kies "Aanmelden met een link per e-mail".{% else %}Kies hier je wachtwoord:

{{ set_password_url }}

Daarna log je in met dit e-mailadres (of je gebruikersnaam, {{ username }}).{% endif %}

Had je deze e-mail niet verwacht? Dan kan je hem negeren.
""",
            "fr-be": """
Bonjour {{ recipient_name }},

{{ guardian_name }} t'a créé ton propre compte CoderDojo. Tu peux y voir ta ceinture,
tes badges et les sessions auxquelles tu as participé, et t'inscrire toi-même à des
sessions.

{% if uses_link %}Tu te connectes avec un lien que nous t'envoyons par e-mail : pas de mot de passe à retenir. Ouvre ce lien dans les {{ valid_days }} jours pour te connecter la première fois :

{{ login_url }}

La prochaine fois, entre cette adresse e-mail sur la page de connexion et choisis « Se connecter avec un lien par e-mail ».{% else %}Choisis ton mot de passe ici :

{{ set_password_url }}

Ensuite, connecte-toi avec cette adresse e-mail (ou ton nom d'utilisateur, {{ username }}).{% endif %}

Tu ne t'attendais pas à cet e-mail ? Tu peux l'ignorer.
""",
        },
    },
    {
        "key": "account_deletion_reminder",
        "category": MailCategory.SERVICE,
        "description": "An unused account will be deleted (privacy.retention). Variables: deletion_date, login_url, "
        "children, volunteer, keeps_profile, champion_of.",
        "subject": {
            "en-us": "Your CoderDojo account will be deleted on {{ deletion_date|date:'j F Y' }}",
            "nl-be": "Je CoderDojo-account wordt op {{ deletion_date|date:'j F Y' }} verwijderd",
            "fr-be": "Votre compte CoderDojo sera supprimé le {{ deletion_date|date:'j F Y' }}",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

Nobody has logged in to your CoderDojo account for almost two years{% if children %}, and
your children haven't used their own logins either{% endif %}. We don't keep data we no
longer need, so on {{ deletion_date|date:"j F Y" }} your account will be
{% if volunteer %}cleaned up.

What stays: your name on the sessions you helped run and on the belts and badges you
awarded{% if keeps_profile %}, and your profile on the dojos' team pages{% endif %}. Everything else goes: your
login, your contact details, your applications and background-check details and your
mail preferences.{% else %}deleted: your login, your contact details and your mail preferences.{% endif %}
{% if children %}
These children go with your account (their details, their own login if they have one,
their belts and badges; the sessions they came to are kept without their name):
{% for child in children %}- {{ child }}
{% endfor %}{% endif %}{% if champion_of %}
You're still the champion of {{ champion_of|join:", " }}. A dojo can't be without its
champion, so your account stays until you hand that role to a mentor (on the dojo's
Team page) or the organisation does.
{% endif %}
Want to keep your account? Just log in before that date{% if children %} (or let one of your
children log in with their own login){% endif %}:

{{ login_url }}
""",
            "nl-be": """
Hallo {{ recipient_name }},

Er is al bijna twee jaar niet meer ingelogd op je CoderDojo-account{% if children %}, en ook je
kinderen gebruikten hun eigen login niet{% endif %}. We bewaren geen gegevens die we niet meer
nodig hebben, dus op {{ deletion_date|date:"j F Y" }} wordt je account
{% if volunteer %}opgeschoond.

Wat blijft: je naam bij de sessies die je mee begeleidde en bij de gordels en badges die
je uitreikte{% if keeps_profile %}, en je profiel op de teampagina's van de dojo's{% endif %}. Al de rest
verdwijnt: je login, je contactgegevens, je aanvragen en de gegevens van je
uittreksel uit het strafregister, en je mailvoorkeuren.{% else %}verwijderd: je login, je contactgegevens en je mailvoorkeuren.{% endif %}
{% if children %}
Deze kinderen verdwijnen mee met je account (hun gegevens, hun eigen login als ze er
een hebben, hun gordels en badges; de sessies waar ze naartoe kwamen blijven bewaard
zonder hun naam):
{% for child in children %}- {{ child }}
{% endfor %}{% endif %}{% if champion_of %}
Je bent nog champion van {{ champion_of|join:", " }}. Een dojo kan niet zonder
champion, dus je account blijft tot je die rol doorgeeft aan een mentor (op de
Team-pagina van de dojo) of de organisatie dat doet.
{% endif %}
Wil je je account houden? Log dan gewoon in voor die datum{% if children %} (of laat een van je
kinderen inloggen met de eigen login){% endif %}:

{{ login_url }}
""",
            "fr-be": """
Bonjour {{ recipient_name }},

Personne ne s'est connecté à votre compte CoderDojo depuis presque deux ans{% if children %}, et
vos enfants n'ont pas non plus utilisé leur propre compte{% endif %}. Nous ne gardons pas les
données dont nous n'avons plus besoin : le {{ deletion_date|date:"j F Y" }}, votre compte sera
{% if volunteer %}nettoyé.

Ce qui reste : votre nom sur les sessions que vous avez encadrées et sur les ceintures
et badges que vous avez remis{% if keeps_profile %}, ainsi que votre profil sur les pages d'équipe des
dojos{% endif %}. Tout le reste disparaît : votre connexion, vos coordonnées, vos candidatures
et les données de votre extrait de casier judiciaire, et vos préférences d'e-mail.{% else %}supprimé : votre connexion, vos coordonnées et vos préférences d'e-mail.{% endif %}
{% if children %}
Ces enfants disparaissent avec votre compte (leurs données, leur propre compte s'ils en
ont un, leurs ceintures et badges ; les sessions auxquelles ils ont participé sont
gardées sans leur nom) :
{% for child in children %}- {{ child }}
{% endfor %}{% endif %}{% if champion_of %}
Vous êtes toujours champion de {{ champion_of|join:", " }}. Un dojo ne peut pas rester
sans champion : votre compte reste donc jusqu'à ce que vous passiez ce rôle à un
mentor (sur la page Équipe du dojo) ou que l'organisation le fasse.
{% endif %}
Vous voulez garder votre compte ? Connectez-vous simplement avant cette date{% if children %} (ou
laissez un de vos enfants se connecter avec son propre compte){% endif %} :

{{ login_url }}
""",
        },
    },
    {
        "key": "youth_mentor_promoted",
        "category": MailCategory.SERVICE,
        "description": "A dojo's team made a child a youth mentor; sent to the family (guardians, plus the "
        "child's own login). Variables: ninja_name, dojo_name, promoted_by, ninja_url.",
        "subject": {
            "en-us": "{{ ninja_name }} is now a youth mentor at {{ dojo_name }}",
            "nl-be": "{{ ninja_name }} is nu youth mentor bij {{ dojo_name }}",
            "fr-be": "{{ ninja_name }} est maintenant jeune mentor à {{ dojo_name }}",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

{% if promoted_by %}{{ promoted_by }}, from the {{ dojo_name }} team,{% else %}The {{ dojo_name }} team{% endif %} has made
{{ ninja_name }} a youth mentor. Youth mentors help other ninjas during sessions and can
be listed on a session's team. They don't get access to the dojo's dashboard.

You can see it on {{ ninja_name }}'s page:

{{ ninja_url }}

Questions, or would you rather {{ ninja_name }} didn't take this role? Get in touch with
the dojo's team, or remove {{ ninja_name }}'s own login on that page: that also ends the
role.
""",
            "nl-be": """
Hallo {{ recipient_name }},

{% if promoted_by %}{{ promoted_by }}, van het team van {{ dojo_name }},{% else %}Het team van {{ dojo_name }}{% endif %} heeft
{{ ninja_name }} youth mentor gemaakt. Youth mentors helpen andere ninja's tijdens de
sessies en kunnen in het team van een sessie staan. Ze krijgen geen toegang tot het
dashboard van de dojo.

Je ziet het op de pagina van {{ ninja_name }}:

{{ ninja_url }}

Vragen, of heb je liever dat {{ ninja_name }} deze rol niet opneemt? Neem contact op met
het team van de dojo, of verwijder de eigen login van {{ ninja_name }} op die pagina:
dan stopt de rol ook.
""",
            "fr-be": """
Bonjour {{ recipient_name }},

{% if promoted_by %}{{ promoted_by }}, de l'équipe de {{ dojo_name }},{% else %}L'équipe de {{ dojo_name }}{% endif %} a fait de
{{ ninja_name }} un jeune mentor. Les jeunes mentors aident les autres ninjas pendant les
sessions et peuvent faire partie de l'équipe d'une session. Ils n'ont pas accès au
tableau de bord du dojo.

Vous le voyez sur la page de {{ ninja_name }} :

{{ ninja_url }}

Des questions, ou vous préférez que {{ ninja_name }} ne prenne pas ce rôle ? Contactez
l'équipe du dojo, ou supprimez le compte de {{ ninja_name }} sur cette page : le rôle
prend fin aussi.
""",
        },
    },
    {
        "key": "campaign_coolest_projects",
        "category": MailCategory.NEWSLETTER,
        "description": "Campaign: invite every active family and volunteer to Coolest Projects. "
        "Variables: signup_url (campaign context).",
        "subject": {
            "en-us": "Show what you made at Coolest Projects!",
            "nl-be": "Toon wat je gemaakt hebt op Coolest Projects!",
            "fr-be": "Montrez vos créations à Coolest Projects !",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

Coolest Projects is the showcase where young makers present what they built:
games, websites, apps, robots, art, anything goes. It doesn't matter whether it's a
first Scratch game or an advanced project: every ninja is welcome to take part, and
mentors and families are welcome to come and have a look.

Have a project to show? Sign up here: {{ signup_url }}

Not sure what to bring yet? Ask the mentors at your next dojo session. They're
happy to help turn an idea into a project.
""",
            "nl-be": """
Hallo {{ recipient_name }},

Coolest Projects is dé plek waar jonge makers tonen wat ze gebouwd hebben: games,
websites, apps, robots, kunst, alles kan. Of het nu een eerste Scratch-game is of
een gevorderd project: elke ninja mag meedoen, en coaches en families zijn welkom om
te komen kijken.

Heb je een project om te tonen? Schrijf je hier in: {{ signup_url }}

Nog geen idee wat je wil tonen? Vraag het aan de coaches op je volgende dojo-sessie.
Ze helpen graag om van een idee een project te maken.
""",
            "fr-be": """
Bonjour {{ recipient_name }},

Coolest Projects, c'est la vitrine où les jeunes créateurs présentent ce qu'ils ont
construit : jeux, sites web, applis, robots, art… tout est possible. Premier jeu
Scratch ou projet avancé, chaque ninja peut participer, et les mentors et les
familles sont les bienvenus pour venir voir.

Vous avez un projet à montrer ? Inscrivez-vous ici : {{ signup_url }}

Pas encore d'idée ? Parlez-en aux mentors lors de votre prochaine session au dojo.
Ils vous aideront volontiers à transformer une idée en projet.
""",
        },
        "unsubscribe": True,
    },
    {
        "key": "campaign_girlz",
        "category": MailCategory.NEWSLETTER,
        "description": "Campaign: CoderDojo Girlz sessions, to families with a daughter or a child "
        "whose gender isn't listed. Variables: signup_url (campaign context).",
        "subject": {
            "en-us": "CoderDojo Girlz: coding sessions especially for girls",
            "nl-be": "CoderDojo Girlz: codeersessies speciaal voor meisjes",
            "fr-be": "CoderDojo Girlz : des sessions de code spécialement pour les filles",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

CoderDojo Girlz are sessions especially for girls: an afternoon of building games,
websites, robots and more, in a group where girls set the tone. No experience
needed, and every level is welcome, from a first Scratch project to advanced coding.

The upcoming Girlz sessions, and how to sign up: {{ signup_url }}

Know someone who'd enjoy it? Feel free to pass this mail on.
""",
            "nl-be": """
Hallo {{ recipient_name }},

CoderDojo Girlz zijn sessies speciaal voor meisjes: een namiddag games, websites,
robots en meer bouwen, in een groep waar meisjes de toon zetten. Geen ervaring
nodig, en elk niveau is welkom, van een eerste Scratch-project tot gevorderd
programmeren.

De volgende Girlz-sessies en inschrijven: {{ signup_url }}

Ken je iemand die dit leuk zou vinden? Stuur deze mail gerust door.
""",
            "fr-be": """
Bonjour {{ recipient_name }},

Les CoderDojo Girlz sont des sessions spécialement pour les filles : un après-midi
pour créer des jeux, des sites web, des robots et plus encore, dans un groupe où les
filles donnent le ton. Aucune expérience requise, tous les niveaux sont les
bienvenus, du premier projet Scratch au code avancé.

Les prochaines sessions Girlz et l'inscription : {{ signup_url }}

Vous connaissez quelqu'un que ça intéresserait ? N'hésitez pas à transférer ce mail.
""",
        },
        "unsubscribe": True,
    },
    {
        "key": "campaign_new_dojo",
        "category": MailCategory.NEWSLETTER,
        "description": "Campaign: a new dojo is opening, to families living near it. "
        "Variables: dojo_name, dojo_path (campaign context), site_url.",
        "subject": {
            "en-us": "A new CoderDojo is opening near you: {{ dojo_name }}",
            "nl-be": "Er opent een nieuwe CoderDojo bij jou in de buurt: {{ dojo_name }}",
            "fr-be": "Un nouveau CoderDojo ouvre près de chez vous : {{ dojo_name }}",
        },
        "body": {
            "en-us": """
Hi {{ recipient_name }},

Good news for young coders in your area: {{ dojo_name }} is opening its doors, close
to where you live.

Like every CoderDojo, it's free and run by volunteers. Ninjas aged 7 to 17 build
games, websites, robots and more at their own pace, with mentors to help them along.
Beginners are very welcome.

See where it is and when the first sessions are: {{ site_url }}{{ dojo_path }}

Already going to another dojo? No need to switch. It's just nice to know there's
one nearby.
""",
            "nl-be": """
Hallo {{ recipient_name }},

Goed nieuws voor jonge programmeurs in je buurt: {{ dojo_name }} opent de deuren,
vlak bij waar je woont.

Zoals elke CoderDojo is het gratis en wordt het gerund door vrijwilligers. Ninja's
van 7 tot 17 jaar bouwen er games, websites, robots en meer, op hun eigen tempo,
met coaches die hen op weg helpen. Beginners zijn van harte welkom.

Bekijk waar het is en wanneer de eerste sessies zijn: {{ site_url }}{{ dojo_path }}

Ga je al naar een andere dojo? Je hoeft niet te wisselen. Het is gewoon fijn om te
weten dat er een dichtbij is.
""",
            "fr-be": """
Bonjour {{ recipient_name }},

Bonne nouvelle pour les jeunes codeurs de votre région : {{ dojo_name }} ouvre ses
portes, tout près de chez vous.

Comme chaque CoderDojo, c'est gratuit et animé par des bénévoles. Les ninjas de 7 à
17 ans y créent des jeux, des sites web, des robots et plus encore, à leur rythme,
accompagnés par des mentors. Les débutants sont les bienvenus.

Découvrez où il se trouve et quand ont lieu les premières sessions : {{ site_url }}{{ dojo_path }}

Vous fréquentez déjà un autre dojo ? Pas besoin de changer : c'est simplement bon à
savoir qu'il y en a un tout près.
""",
        },
        "unsubscribe": True,
    },
]


def template_rows():
    """Every seeded EmailTemplate as field dicts, one per key and language."""
    for entry in TEMPLATES:
        for language, subject in entry["subject"].items():
            yield {
                "key": entry["key"],
                "language": language,
                "category": entry["category"],
                "description": entry["description"],
                "subject": subject,
                "body": _body(language, entry["body"][language], entry.get("unsubscribe", False)),
            }


# Stands in for the id of the dojo that's opening; seed_mailing picks a real
# one (a draft dojo with a location, else the newest active one).
NEW_DOJO = "new_dojo"

# "Active" in the seeded "Everyone active" segment: a volunteer whose dojo
# held a session, or a child who came to one, within this many days. The
# same window on both sides.
ACTIVE_WITHIN_DAYS = 365

_start = datetime(2026, 10, 3, 14, 0)
_event = {
    "ninja_name": "Emma",
    "event_name": "Scratch for beginners",
    "dojo_name": "CoderDojo Ghent",
    "start_time": _start,
    "end_time": datetime(2026, 10, 3, 17, 0),
    "venue": "Ghent Public Library",
    "event_url": "https://coolregistration.localhost/events/1/",
    "account_url": "https://coolregistration.localhost/account/",
}
_common = {
    "recipient_name": "Ellen",
    "site_url": "https://coolregistration.localhost",
    "unsubscribe_url": "https://coolregistration.localhost/mail/unsubscribe/example/",
}
SAMPLE_CONTEXT = {
    "registration_confirmed": {**_common, **_event},
    "waitlist_promoted": {**_common, **_event},
    "registration_waitlisted": {**_common, **_event},
    "session_reminder": {**_common, **_event},
    "new_sessions_at_dojo": {
        **_common,
        "dojo_name": "CoderDojo Ghent",
        "dojo_url": "https://coolregistration.localhost/dojos/1/",
        "events": [
            {
                "name": "Scratch for beginners",
                "start_time": _start,
                "url": "https://coolregistration.localhost/events/1/",
            },
            {
                "name": "Python games",
                "start_time": datetime(2026, 10, 17, 14, 0),
                "url": "https://coolregistration.localhost/events/2/",
            },
        ],
    },
    "background_check_requested": {
        **_common,
        "upload_url": "https://coolregistration.localhost/background-check/example/",
    },
    "background_check_validated": {**_common, "expires_at": datetime(2027, 9, 25)},
    "background_check_rejected": {**_common, "account_url": "https://coolregistration.localhost/account/"},
    "background_check_expiring": {
        **_common,
        "expires_at": datetime(2026, 10, 29),
        "account_url": "https://coolregistration.localhost/account/",
    },
    "background_checks_waiting": {
        **_common,
        "count": 3,
        "oldest": datetime(2026, 9, 22),
        "checks_url": "https://coolregistration.localhost/manage/checks/",
    },
    "application_approved": {
        **_common,
        "kind": "mentor",
        "join_dojo_name": "CoderDojo Ghent",
        "account_url": "https://coolregistration.localhost/account/",
    },
    "application_rejected": {**_common},
    "password_reset": {
        **_common,
        "reset_url": "https://coolregistration.localhost/password-reset/confirm/MQ/abc-123/",
    },
    "email_change_confirm": {
        **_common,
        "new_email": "ellen.new@example.com",
        "old_email": "ellen@example.com",
        "confirm_url": "https://coolregistration.localhost/account/email/confirm/abc-123/",
        "valid_hours": 24,
        "by_organisation": False,
        "by_guardian": "",
    },
    "email_changed": {
        **_common,
        "new_email": "ellen.new@example.com",
        "changed_at": datetime(2026, 10, 3, 14, 30),
        "contact_url": "https://coolregistration.localhost/contact/",
    },
    "login_link": {
        **_common,
        "login_url": "https://coolregistration.localhost/login/link/MQ/abc-123/",
        "first": False,
        "valid_minutes": 15,
        "valid_days": 3,
    },
    "login_link_not_available": {
        **_common,
        "reset_url": "https://coolregistration.localhost/password-reset/confirm/MQ/abc-123/",
        "security_url": "https://coolregistration.localhost/account/security/",
    },
    "login_method_confirm": {
        **_common,
        "confirm_url": "https://coolregistration.localhost/account/security/login-method/confirm/MQ/abc-123/",
        "valid_hours": 24,
    },
    "login_method_changed": {
        **_common,
        "method": "link",
        "by_guardian": "",
        "security_url": "https://coolregistration.localhost/account/security/",
        "contact_url": "https://coolregistration.localhost/contact/",
    },
    "child_login_changed": {
        **_common,
        "child_name": "Emma",
        "child_url": "https://coolregistration.localhost/account/ninja/1/",
        "change": "login_method_changed",
        "method": "link",
        "new_email": "emma@example.com",
        "by_guardian": "",
    },
    "organisation_invitation": {
        **_common,
        "invited_by": "Priya Nair",
        "roles": ["reviewer"],
        "accept_url": "https://coolregistration.localhost/invitation/abc-123/",
        "valid_days": 14,
    },
    "organisation_role_changed": {
        **_common,
        "roles": ["admin", "reviewer"],
        "changed_by": "Priya Nair",
        "manage_url": "https://coolregistration.localhost/manage/",
        "contact_url": "https://coolregistration.localhost/contact/",
    },
    "two_step_turned_on": {
        **_common,
        "method": "app",
        "security_url": "https://coolregistration.localhost/account/security/",
    },
    "two_step_method_added": {
        **_common,
        "method": "passkey",
        "security_url": "https://coolregistration.localhost/account/security/",
    },
    "two_step_method_removed": {
        **_common,
        "method": "passkey",
        "security_url": "https://coolregistration.localhost/account/security/",
    },
    "two_step_turned_off": {
        **_common,
        "by_organisation": False,
        "by_guardian": "",
        "security_url": "https://coolregistration.localhost/account/security/",
    },
    "backup_code_used": {
        **_common,
        "codes_left": 9,
        "security_url": "https://coolregistration.localhost/account/security/",
    },
    "youth_mentor_promoted": {
        **_common,
        "ninja_name": "Emma",
        "dojo_name": "CoderDojo Ghent",
        "promoted_by": "Jan Peeters",
        "ninja_url": "https://coolregistration.localhost/account/ninja/1/",
    },
    "ninja_account_created": {
        **_common,
        "recipient_name": "Emma",
        "guardian_name": "Ellen Peeters",
        "username": "emma",
        "uses_link": False,
        "set_password_url": "https://coolregistration.localhost/password-reset/confirm/MQ/abc-123/",
        "login_url": "https://coolregistration.localhost/login/link/MQ/abc-123/",
        "valid_days": 3,
    },
    "account_deletion_reminder": {
        **_common,
        "deletion_date": datetime(2026, 10, 26),
        "login_url": "https://coolregistration.localhost/login/",
        "children": ["Emma", "Lucas"],
        "volunteer": False,
        "keeps_profile": False,
        "champion_of": [],
    },
    "campaign_coolest_projects": {**_common, "signup_url": "https://coolestprojects.org"},
    "campaign_girlz": {**_common, "signup_url": "https://coolregistration.localhost/events/"},
    "campaign_new_dojo": {**_common, "dojo_name": "CoderDojo Aalter", "dojo_path": "/dojos/1/"},
}

# The two example campaigns, with the segment each one uses. Seeded as
# drafts: nothing is sent until an admin launches them.
CAMPAIGNS = [
    {
        "name": "Coolest Projects",
        "template_key": "campaign_coolest_projects",
        "context": {"signup_url": "https://coolestprojects.org"},
        "segment": {
            "name": "Everyone active",
            "description": f"Champions and mentors (active membership) of active dojos that held a session in "
            f"the last {ACTIVE_WITHIN_DAYS} days, and parents of a child who came to a session "
            f"in the last {ACTIVE_WITHIN_DAYS} days.",
            "groups": [
                {
                    "scope": "user",
                    "operator": "or",
                    "rules": [("active_team_member", "within_days", ACTIVE_WITHIN_DAYS)],
                    "children": [
                        {
                            "scope": "ninja",
                            "operator": "and",
                            "rules": [("attended_within_days", "within_days", ACTIVE_WITHIN_DAYS)],
                        },
                    ],
                },
            ],
        },
    },
    {
        "name": "CoderDojo Girlz",
        "template_key": "campaign_girlz",
        "context": {"signup_url": "https://coolregistration.localhost/events/"},
        "segment": {
            "name": "Families with girls (or gender not listed)",
            "description": "Parents of a child whose gender is girl or not given (“Prefer not to say”).",
            "groups": [
                {"scope": "ninja", "operator": "and", "rules": [("ninja_gender", "in", ["girl", "unspecified"])]},
            ],
        },
    },
    {
        "name": "New dojo opening",
        "template_key": "campaign_new_dojo",
        # dojo_name/dojo_path are filled in for the chosen dojo by seed_mailing.
        "context": {},
        "segment": {
            "name": "Families near the new dojo",
            "description": "Every family (an account with children) whose postcode is within 20 km of the new dojo.",
            "groups": [
                {
                    "scope": "user",
                    "operator": "and",
                    "rules": [
                        ("has_children", "is", True),
                        ("near_dojo", "within", {"dojo": NEW_DOJO, "km": 20}),
                    ],
                },
            ],
        },
    },
]

# The templates the site itself sends (everything but the campaign
# examples): they can be edited, never deleted, and their English version
# (the fallback for every language) always stays.
SYSTEM_TEMPLATE_KEYS = {entry["key"] for entry in TEMPLATES if entry["category"] != MailCategory.NEWSLETTER}

# Example data for previewing a template nobody wrote a sample for yet.
GENERIC_SAMPLE_CONTEXT = {
    "recipient_name": "Ellen",
    "site_url": "https://coolregistration.localhost",
    "unsubscribe_url": "https://coolregistration.localhost/mail/unsubscribe/example/",
}
