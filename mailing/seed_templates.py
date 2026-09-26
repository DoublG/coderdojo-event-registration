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
        "key": "ninja_account_created",
        "category": MailCategory.SERVICE,
        "description": "A guardian gave their child their own login (or switched it back on). Sent to the "
                       "child's address. Variables: guardian_name, username, set_password_url.",
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

Choose your password here:

{{ set_password_url }}

After that, log in with this email address (or your username, {{ username }}).

Didn't expect this mail? Then you can ignore it.
""",
            "nl-be": """
Hallo {{ recipient_name }},

{{ guardian_name }} heeft een eigen CoderDojo-login voor je gemaakt. Daarmee zie je je
gordel, je badges en de sessies waar je naartoe ging, en kan je je zelf inschrijven
voor sessies.

Kies hier je wachtwoord:

{{ set_password_url }}

Daarna log je in met dit e-mailadres (of je gebruikersnaam, {{ username }}).

Had je deze e-mail niet verwacht? Dan kan je hem negeren.
""",
            "fr-be": """
Bonjour {{ recipient_name }},

{{ guardian_name }} t'a créé ton propre compte CoderDojo. Tu peux y voir ta ceinture,
tes badges et les sessions auxquelles tu as participé, et t'inscrire toi-même à des
sessions.

Choisis ton mot de passe ici :

{{ set_password_url }}

Ensuite, connecte-toi avec cette adresse e-mail (ou ton nom d'utilisateur, {{ username }}).

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
            {"name": "Scratch for beginners", "start_time": _start, "url": "https://coolregistration.localhost/events/1/"},
            {"name": "Python games", "start_time": datetime(2026, 10, 17, 14, 0),
             "url": "https://coolregistration.localhost/events/2/"},
        ],
    },
    "background_check_requested": {**_common, "upload_url": "https://coolregistration.localhost/background-check/example/"},
    "background_check_validated": {**_common, "expires_at": datetime(2027, 9, 25)},
    "background_check_rejected": {**_common, "account_url": "https://coolregistration.localhost/account/"},
    "application_approved": {**_common, "kind": "mentor", "join_dojo_name": "CoderDojo Ghent",
                             "account_url": "https://coolregistration.localhost/account/"},
    "application_rejected": {**_common},
    "password_reset": {**_common, "reset_url": "https://coolregistration.localhost/password-reset/confirm/MQ/abc-123/"},
    "youth_mentor_promoted": {
        **_common, "ninja_name": "Emma", "dojo_name": "CoderDojo Ghent", "promoted_by": "Jan Peeters",
        "ninja_url": "https://coolregistration.localhost/account/ninja/1/",
    },
    "ninja_account_created": {
        **_common, "recipient_name": "Emma", "guardian_name": "Ellen Peeters", "username": "emma",
        "set_password_url": "https://coolregistration.localhost/password-reset/confirm/MQ/abc-123/",
    },
    "account_deletion_reminder": {
        **_common, "deletion_date": datetime(2026, 10, 26), "login_url": "https://coolregistration.localhost/login/",
        "children": ["Emma", "Lucas"], "volunteer": False, "keeps_profile": False,
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
                {"scope": "user", "operator": "or", "rules": [("active_team_member", "within_days", ACTIVE_WITHIN_DAYS)],
                 "children": [
                     {"scope": "ninja", "operator": "and",
                      "rules": [("attended_within_days", "within_days", ACTIVE_WITHIN_DAYS)]},
                 ]},
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
                {"scope": "user", "operator": "and", "rules": [
                    ("has_children", "is", True),
                    ("near_dojo", "within", {"dojo": NEW_DOJO, "km": 20}),
                ]},
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
