# Dutch texts for the user-journey PDFs (informal "je", like the site).
UI = {
    "brand": "CoderDojo België · gebruikersreis",
    "who": "Schermafbeeldingen van de ontwikkelsite (demogegevens), ingelogd als <b>{who}</b>, 29 september 2026.",
    "journey": "De reis",
    "steps": "Stappen in dit document",
    "foot": "coolregistration.localhost · gemaakt vanuit de draaiende applicatie",
    "step": "Stap",
    "continued": "(vervolg)",
    "footer": "CoderDojo België · reis van de {title}",
}

WHO = {
    "parent": "guardian-5 (ouder van Lotte, 14, en Olivia, 16)",
    "ninja": "guardian-5-child-1 (Lotte, 14, eigen login, thuisdojo Zonnebeke)",
    "volunteer": "guardian-11 / guardian-2 / guardian-3 (kandidaten) en mentor-51-1 (mentor bij Dojo Westerlo)",
    "champion": "owner-51-dojo-westerlo (champion van Dojo Westerlo)",
    "reviewer": "org-sofie-claes (rol beoordelaar bij de organisatie, aanmelden in twee stappen)",
    "organisation": "org-priya-nair (rol beheerder bij de organisatie, aanmelden in twee stappen)",
}

INTRO = {
    "parent": (
        "Ouder",
        "Een ouder of voogd zoekt een dojo, maakt een gezinsaccount en schrijft de kinderen in voor sessies. Ouders hebben geen goedkeuring of uittreksel uit het strafregister nodig: ze beheren alleen hun eigen kinderen.",
        [
            "Dojo's en sessies ontdekken zonder account",
            "In één keer een gezinsaccount maken met de kinderen",
            "De gordels, badges en geschiedenis van elk kind volgen",
            "Inschrijven voor een sessie en de bevestigingsmail krijgen",
            "E-mail, aanmeldbeveiliging en privacy beheren",
        ],
    ),
    "ninja": (
        "Ninja",
        "Een kind van 7 tot 17 jaar dat naar een dojo komt. De meeste ninja's loggen nooit in; een ouder kan hen een eigen login geven, zodat ze hun vorderingen volgen en zichzelf inschrijven.",
        [
            "Inloggen met de login die een ouder instelde",
            "Gordels, badges en sessiegeschiedenis bekijken",
            "Leertrajecten ontdekken",
            "Zichzelf inschrijven voor een sessie",
            "De eigen aanmeldbeveiliging beheren",
        ],
    ),
    "volunteer": (
        "Vrijwilliger (mentor)",
        "Een volwassene die wil helpen in een dojo. Mentor worden is een eenmalige goedkeuring van het account: een aanvraag plus een geldig uittreksel uit het strafregister. Daarna kan je bij het team van elke dojo komen en mee sessies begeleiden.",
        [
            "Aanvragen om mentor te worden (of een dojo te starten)",
            "Het uittreksel uploaden wanneer erom gevraagd wordt",
            "Wachten op de beslissing van de beoordelaars",
            "Werken in de beheeromgeving van de dojo: sessies en aanwezigheden",
            "Gordels en badges toekennen, het team beheren, bij andere dojo's aansluiten",
        ],
    ),
    "champion": (
        "Champion",
        "De persoon die een dojo leidt. De champion kan alles wat een mentor kan, plus de status van de dojo, de gezondheidsinfo van de kinderen, e-mail aan de gezinnen van de dojo en de API-clients van de dojo.",
        [
            "Het dashboard en de volgende sessie opvolgen",
            "Het publieke profiel van de dojo bijhouden",
            "Sessies plannen en publiceren, de wachtlijst opvolgen",
            "Aanwezigheden nemen, het team en de leden beheren",
            "Nieuws plaatsen, gezinnen mailen, apps koppelen",
        ],
    ),
    "reviewer": (
        "Beoordelaar",
        "Een rol bij de organisatie die alleen uittreksels uit het strafregister beoordeelt en over aanvragen van vrijwilligers beslist, in de groep Vrijwilligers van het organisatiedashboard.",
        [
            "Aanmelden in twee stappen",
            "De wachtrij van uittreksels afwerken",
            "Een document goedkeuren of weigeren (daarna wordt het verwijderd)",
            "Aanvragen voor mentor en champion goedkeuren of weigeren",
        ],
    ),
    "organisation": (
        "Beheerder bij de organisatie",
        "De medewerkers en het bestuur van CoderDojo België. Het organisatiedashboard omvat communicatie, de publieke site, badges, privacyverzoeken, mensen en beveiliging; de Django-admin is alleen voor technische ingrepen, op aanvraag.",
        [
            "E-mailcampagnes, segmenten, trajecten en sjablonen",
            "De e-mailwachtrij opvolgen",
            "Uitgelichte evenementen, sponsors en badges",
            "Privacyverzoeken, mensen en rollen, aanmeldbeleid",
            "Auditlog en Django-admin voor beperkte tijd",
        ],
    ),
}

STEPS = {
    "parent": {
        "home": (
            "CoderDojo ontdekken",
            "Een ouder komt op de startpagina. De dojozoeker en de carrousel met komende sessies staan er meteen, zonder account.",
        ),
        "finder": (
            "Een dojo in de buurt vinden",
            "De dojozoeker sorteert dojo's op afstand van een ingetypt adres, de locatie van de browser of (ingelogd) de postcode van het gezin.",
        ),
        "dojo": (
            "De pagina van een dojo",
            "Elke dojo heeft een pagina met zijn talen, volgende sessies, team, nieuws en de leertrajecten die hij aanbiedt.",
        ),
        "events": ("Sessies bekijken", "Alle komende sessies, te filteren op regio, taal, leeftijd en leertraject."),
        "event-full": (
            "Een volle sessie",
            "Als een sessie vol is, kunnen gezinnen nog op de wachtlijst; ze schuiven automatisch door als er een plaats vrijkomt.",
        ),
        "signup": (
            "Een gezinsaccount maken",
            "Zelf inschrijven: de gegevens van de ouder, een rij per kind (meer met 'Nog een kind toevoegen'), de taal van de mails en optionele toestemmingen. Geen goedkeuring nodig.",
        ),
        "account": (
            "De accountpagina van het gezin",
            "Na het inloggen toont de accountpagina de gegevens van de ouder (ter plaatse aan te passen), elk kind, hun komende plaatsen (en plaats op de wachtlijst) en links naar e-mailvoorkeuren, beveiliging en privacy.",
        ),
        "child": (
            "De pagina van een kind",
            "Per kind: gegevens, gordel, badges, bezochte en komende sessies, en of het kind een eigen login heeft.",
        ),
        "event": ("Een sessie kiezen", "De ouder opent een sessie in de thuisdojo van het kind."),
        "pick-children": (
            "Kiezen welke kinderen gaan",
            "De inschrijfpagina toont de kinderen van het gezin; wie al ingeschreven is, staat aangeduid.",
        ),
        "picked": ("Bevestigen", "Vink de kinderen aan en bevestig."),
        "confirmed": (
            "Ingeschreven",
            "De plaats is meteen bevestigd (of het kind komt op de wachtlijst) en er staat een bevestigingsmail klaar.",
        ),
        "mail": (
            "De bevestigingsmail",
            "De bevestiging komt aan in de taal die de ouder koos. Tijdens de ontwikkeling komt elke mail in Mailpit terecht.",
        ),
        "mail-prefs": (
            "E-mailvoorkeuren",
            "De ouder kiest welke soorten mail hij krijgt, zet het nieuws van een dojo uit, en geeft of trekt toestemming in per kind.",
        ),
        "security": (
            "Aanmeldbeveiliging",
            "Optioneel aanmelden in twee stappen (authenticator-app, passkeys, back-upcodes), of inloglinks in plaats van een wachtwoord.",
        ),
        "delete": (
            "Privacy: downloaden of verwijderen",
            "Vanaf de accountpagina downloadt het gezin al zijn gegevens, of verwijdert het account na bevestiging met het wachtwoord.",
        ),
    },
    "ninja": {
        "login": (
            "Inloggen met een eigen login",
            "Een ouder kan een kind (7–17) een eigen login geven, met een wachtwoord of inloglinks (aanmelden in twee stappen kan ook). Het kind logt in met de gebruikersnaam die de ouder kreeg.",
        ),
        "me": (
            "Mijn gordels, badges en geschiedenis",
            "De ninja ziet zijn huidige gordel en wie die toekende, de badges (met de vooruitgang naar het volgende polsbandje) en elke sessie waar hij was. Kijken mag, aanpassen niet: de gegevens blijven bij de ouder (alleen de avatar kiest de ninja zelf, uit de standaardset).",
        ),
        "pathway": (
            "Een leertraject ontdekken",
            "Leertrajecten (Scratch, Python, webontwikkeling, ...) tonen de stappen en projecten die een ninja in de dojo kan doorlopen.",
        ),
        "event": ("De volgende sessie zoeken", "De ninja bekijkt sessies zoals iedereen ..."),
        "signup": (
            "... en schrijft zichzelf in",
            "Met een eigen login kan een ninja alleen zichzelf inschrijven. De ouder krijgt nog altijd de bevestigingsmail.",
        ),
        "done": (
            "Plaats bevestigd",
            "De plaats is bevestigd en staat op de pagina van de ninja en op de accountpagina van de ouder, waar ze allebei kunnen annuleren.",
        ),
        "security": (
            "De eigen aanmeldbeveiliging",
            "De login van een ninja heeft dezelfde aanmeldopties als die van een volwassene, aanmelden in twee stappen inbegrepen. De ouder krijgt bericht van elke wijziging.",
        ),
    },
    "volunteer": {
        "register": (
            "Vrijwilliger worden",
            "De aanmeldpagina legt de mogelijkheden uit: een gezinsaccount, helpen in een dojo als mentor, of een dojo starten als champion. Vrijwilligers gebruiken eerst een gewoon account.",
        ),
        "apply-mentor": (
            "Aanvragen om mentor te worden",
            "Ingelogd kan elke volwassene aanvragen om mentor te worden: eventueel met een dojo, vaardigheden en beschikbaarheid, en akkoord met het uittreksel uit het strafregister. De goedkeuring als mentor geldt één keer per account, niet per dojo.",
        ),
        "apply-champion": (
            "Of een dojo starten",
            "Een dojo starten is de aanvraag als champion: regio, voorgestelde locatie en planning. Een goedgekeurde champion maakt zelf zijn dojo aan.",
        ),
        "check-requested": (
            "Het uittreksel wordt gevraagd",
            "Na de aanvraag vraagt een beoordelaar het uittreksel uit het strafregister (model 2). De accountpagina en een gemailde link leiden allebei naar de upload.",
        ),
        "upload": (
            "Het document uploaden",
            "Het document wordt privé bewaard (geen publieke URL), alleen de beoordelaars zien het, en het wordt verwijderd zodra ze beslissen: alleen de beslissing blijft bewaard.",
        ),
        "waiting": (
            "Wachten op beoordeling",
            "Na de upload toont het account dat het uittreksel op een beoordelaar wacht. Beoordelaars krijgen elke dag een mail zolang er documenten wachten.",
        ),
        "landing": (
            "Een goedgekeurde mentor logt in",
            "Eens goedgekeurd en in het team van een dojo, gaat inloggen meteen naar de beheeromgeving van de dojo. De keuzelijst bovenaan de zijbalk toont elke dojo waar ze helpen.",
        ),
        "events": (
            "De sessies van de dojo",
            "Mentors zien en beheren de sessies van de dojo: publiceren, inschrijvingen sluiten, heropenen.",
        ),
        "event": (
            "Eén sessie",
            "De gegevens, status, het team en de leertrajecten van de sessie, ter plaatse aan te passen, plus een link om aanwezigheden te nemen.",
        ),
        "attendance": (
            "Aanwezigheden nemen aan de deur",
            "Op de dag zelf duidt de mentor elk kind aan als aanwezig of afwezig (htmx, zonder de pagina te herladen). Elke rij toont de gordel van het kind, hoe regelmatig het komt en 'Op bezoek' voor kinderen van een andere dojo; ook het team van de sessie staat erbij, voor de verzekering.",
        ),
        "marked": (
            "Aanwezig",
            "Eén klik duidt een kind aan als aanwezig en past de teller 'N van M aanwezig' aan. Mijlpaalbadges (polsbandjes) volgen de aanwezigheden automatisch.",
        ),
        "belt": (
            "Een gordel toekennen",
            "Mentors kennen gordels en eenmalige badges toe vanuit dezelfde lijst. De gordelgeschiedenis wordt alleen aangevuld en bewaart wie de gordel toekende en in welke rol.",
        ),
        "team": (
            "Het team van de dojo",
            "Elke actieve mentor kan aanvragen om bij het team te komen aanvaarden, goedgekeurde mentors toevoegen en een ninja promoveren tot youth mentor.",
        ),
        "join": (
            "Bij een andere dojo aansluiten",
            "Een goedgekeurde mentor kan vanaf de publieke pagina van elke dojo vragen om bij het team te komen; het team aanvaardt of weigert.",
        ),
    },
    "champion": {
        "dashboard": (
            "Het dashboard van de dojo",
            "De startpagina van de champion: de aanwezigheden van de volgende sessie, een banner als de dojo niet actief is, en een seintje na zes maanden zonder sessies.",
        ),
        "settings": (
            "Instellingen van de dojo",
            "Bovenaan de status van de dojo: alleen de champion lanceert de dojo, zet hem op slapend of archiveert hem (nooit met open sessies) en heropent hem. Daaronder alles op de publieke pagina van de dojo: naam, beschrijving in elke taal van de dojo, icoon, adres (opnieuw gelokaliseerd bij het opslaan), contactgegevens en leertrajecten.",
        ),
        "events": (
            "Sessies",
            "Alle sessies van de dojo met hun status (concept, open, gesloten) en de volgende stap in één klik.",
        ),
        "new-event": (
            "Een nieuwe sessie plannen",
            "Een nieuwe sessie: datum en uren (Belgische notatie), plaatsen, leeftijden, doelgroep (bv. een sessie voor meisjes), een banner uit de beeldbibliotheek of een upload, het team en de leertrajecten. Ze start als concept; publiceren opent de inschrijvingen en de gezinnen krijgen de mail met nieuwe sessies.",
        ),
        "event": (
            "Een volle sessie met wachtlijst",
            "De pagina van de sessie toont de ingenomen plaatsen en de wachtlijst; als een gezin annuleert, schuift het eerste wachtende kind door en krijgt dat gezin een mail.",
        ),
        "attendance": (
            "Aanwezigheden met gezondheidsinfo",
            "De aanwezigheidslijst van de champion toont ook de allergieën en gezondheidsinfo van het gezin, alleen voor kinderen met een bevestigde plaats, en elke keer dat iemand ze bekijkt komt in de auditlog.",
        ),
        "team": (
            "Het team beheren",
            "Aanvragen om bij het team te komen aanvaarden, mentors toevoegen, youth mentors promoveren, en de rol van champion overdragen aan een actieve mentor.",
        ),
        "members": (
            "Leden",
            "De kinderen met deze dojo als thuisdojo, met een knop om er een tot youth mentor te promoveren.",
        ),
        "updates": ("Nieuws", "Korte berichten 'Van deze dojo' op de publieke pagina van de dojo."),
        "mail": (
            "Mail aan de gezinnen",
            "De champion schrijft de gezinnen van de dojo (of het eigen team), hoogstens een paar keer per maand. Het team ziet aantallen, nooit de adressen van gezinnen.",
        ),
        "mail-new": (
            "Een mail schrijven",
            "Onderwerp en bericht in elke taal van de dojo en een klaargezet publiek (alle gezinnen, de leeftijd of gordel van een kind, ...). Gezinnen antwoorden rechtstreeks naar het adres van de dojo en kunnen het nieuws van één dojo uitzetten.",
        ),
        "api": (
            "API-clients",
            "Voor apps die voor de dojo werken (bv. kinderen aan de deur inscannen): OAuth 2.0 client credentials met aanwezigheidsrechten, alleen voor de champion.",
        ),
    },
    "reviewer": {
        "login-2fa": (
            "Aanmelden in twee stappen",
            "Beoordelaars zien uittreksels uit het strafregister, dus dit account meldt zich na het wachtwoord aan met een code uit een authenticator-app (passkeys en back-upcodes werken ook). De organisatie kan dit per rol verplichten.",
        ),
        "checks": (
            "Uittreksels",
            "De beoordelaar komt in de groep Vrijwilligers, de enige pagina's die deze rol opent. De wachtrij: documenten die wachten op beoordeling, uittreksels die op een document wachten, en verlopen of bijna verlopen uittreksels.",
        ),
        "check": (
            "Eén uittreksel beoordelen",
            "Het uittreksel van één persoon: download het document en keur het goed of weiger het. Beide beslissingen verwijderen het document meteen; alleen de beslissing, de beoordelaar en de vervaldatum blijven bewaard. Het openen van deze pagina komt in de auditlog.",
        ),
        "applications": (
            "Aanvragen",
            "Aanvragen voor mentor en champion, met de stand van het uittreksel van elke kandidaat.",
        ),
        "application": (
            "Over een aanvraag beslissen",
            "Met een geldig uittreksel keurt de beoordelaar goed (een goedgekeurde mentor kan dan bij dojo's aansluiten, een champion er een maken) of weigert. Niemand beslist over zijn eigen aanvraag of uittreksel.",
        ),
    },
    "organisation": {
        "campaigns": (
            "Campagnes",
            "Inloggen (in twee stappen) brengt je naar het organisatiedashboard. De zijbalk groepeert de pagina's per domein (Communicatie, Publieke site, Ninja's, Accounts, Organisatie), en de keuzelijst toont ook de eigen evenementen van de organisatie (Coolest Projects, CoderDojo Girlz). Campagnes zijn eenmalige mailings, met hun resultaten (in de wachtrij, verstuurd, teruggekomen, tegengehouden).",
        ),
        "campaign": (
            "Een campagne",
            "Een concept bewerken, bekijken in elke taal, het aantal ontvangers en een steekproef zien, jezelf een test sturen, en lanceren (nu of gepland). Het publiek wordt vastgelegd bij de lancering.",
        ),
        "segments": ("Segmenten", "Doelgroepen beschreven zonder code, met live aantallen."),
        "segment": (
            "De segmentbouwer",
            "Groepen regels over accounts of over 'hetzelfde kind' (leeftijd, gender, gordel, thuisdojo, betrokkenheid, afstand tot een dojo, ...), met EN of OF gecombineerd en genest. Regels over kinderen bereiken alleen ouders die toestemming gaven.",
        ),
        "journeys": (
            "Trajecten",
            "Doorlopende campagnes die dagelijks lopen, bv. een mail 'we missen je' in de week dat een kind dreigt af te haken.",
        ),
        "templates": (
            "E-mailsjablonen",
            "Elke mail die de site verstuurt, in het Engels, Nederlands en Frans, en wat hem gebruikt.",
        ),
        "queue": (
            "E-mailwachtrij",
            "Wachtende en mislukte mail, teruggekomen mail en geblokkeerde adressen, met een waarschuwing als de workers stil lijken te liggen.",
        ),
        "promotions": (
            "Uitgelicht",
            "Evenementen (bv. Coolest Projects) een tijdlang uitlichten op de startpagina en elders.",
        ),
        "sponsors": ("Sponsors", "'Mogelijk gemaakt door' op de startpagina."),
        "awards": (
            "Badges",
            "Alleen de organisatie maakt badges: eenmalige badges die dojo's toekennen, en mijlpaalbadges voor aanwezigheden (die een gordel kunnen opleveren).",
        ),
        "privacy": (
            "Privacyverzoeken",
            "Elk account opzoeken om de gegevens te downloaden, het e-mailadres te wijzigen of het te verwijderen, en de accounts zien die de bewaartermijn tegenhoudt.",
        ),
        "people": (
            "Mensen",
            "Wie welke rol heeft bij de organisatie (beheerder, bestuur, beoordelaar), uitnodigingen voor mensen zonder account, en open toegang tot de Django-admin.",
        ),
        "security": (
            "Aanmeldbeleid",
            "Welke rollen vanaf welke datum in twee stappen of met een passkey moeten aanmelden; en iemands aanmelden in twee stappen uitzetten als die zijn telefoon kwijt is.",
        ),
        "audit": (
            "Auditlog",
            "Wie wat wijzigde, en wie gevoelige gegevens bekeek. Alleen lezen; gezondheids- en beveiligingsvelden blijven verborgen.",
        ),
        "django-admin": (
            "Django-admin op aanvraag",
            "De Django-admin is alleen voor technische ingrepen: een rol bij de organisatie vraagt hem aan met een reden en het wachtwoord, voor 12 uur, en de andere beheerders krijgen bericht.",
        ),
    },
}
