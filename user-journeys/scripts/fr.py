# French texts for the user-journey PDFs ("vous", like the site; terms as in locale/fr_BE).
UI = {
    "brand": "CoderDojo Belgique · parcours utilisateur",
    "who": "Captures d'écran du site de développement (données de démonstration), connecté en tant que <b>{who}</b>, 29 septembre 2026.",
    "journey": "Le parcours",
    "steps": "Étapes de ce document",
    "foot": "coolregistration.localhost · généré à partir de l'application en service",
    "step": "Étape",
    "continued": "(suite)",
    "footer": "CoderDojo Belgique · parcours : {title}",
}

WHO = {
    "parent": "guardian-5 (parent de Lotte, 14 ans, et d'Olivia, 16 ans)",
    "ninja": "guardian-5-child-1 (Lotte, 14 ans, propre compte, dojo d'attache Zonnebeke)",
    "volunteer": "guardian-11 / guardian-2 / guardian-3 (candidats) et mentor-51-1 (mentor au Dojo Westerlo)",
    "champion": "owner-51-dojo-westerlo (champion du Dojo Westerlo)",
    "reviewer": "org-sofie-claes (rôle d'évaluateur à l'organisation, connexion en deux étapes)",
    "organisation": "org-priya-nair (rôle d'administrateur à l'organisation, connexion en deux étapes)",
}

INTRO = {
    "parent": (
        "Parent",
        "Un parent ou tuteur trouve un dojo, crée un compte famille et inscrit ses enfants aux sessions. Les parents n'ont besoin ni d'approbation ni d'extrait de casier judiciaire : ils ne gèrent que leurs propres enfants.",
        [
            "Découvrir les dojos et les sessions sans compte",
            "Créer en une fois un compte famille avec les enfants",
            "Suivre les ceintures, badges et l'historique de chaque enfant",
            "Inscrire à une session et recevoir l'e-mail de confirmation",
            "Gérer les e-mails, la sécurité de connexion et la vie privée",
        ],
    ),
    "ninja": (
        "Ninja",
        "Un enfant de 7 à 17 ans qui fréquente un dojo. La plupart des ninjas ne se connectent jamais ; un parent peut leur donner leur propre compte, pour suivre leurs progrès et s'inscrire eux-mêmes.",
        [
            "Se connecter avec le compte créé par un parent",
            "Voir ses ceintures, badges et l'historique des sessions",
            "Découvrir les parcours d'apprentissage",
            "S'inscrire soi-même à une session",
            "Gérer sa propre sécurité de connexion",
        ],
    ),
    "volunteer": (
        "Bénévole (mentor)",
        "Un adulte qui veut aider dans un dojo. Devenir mentor est une approbation unique du compte : une candidature et un extrait de casier judiciaire valable. Ensuite, il peut rejoindre l'équipe de n'importe quel dojo et animer des sessions.",
        [
            "Poser sa candidature comme mentor (ou pour lancer un dojo)",
            "Envoyer l'extrait de casier quand il est demandé",
            "Attendre la décision des évaluateurs",
            "Travailler dans l'espace de gestion du dojo : sessions et présences",
            "Décerner ceintures et badges, gérer l'équipe, rejoindre d'autres dojos",
        ],
    ),
    "champion": (
        "Champion",
        "La personne qui dirige un dojo. Le champion peut tout ce que peut un mentor, plus le statut du dojo, les informations de santé des enfants, les e-mails aux familles du dojo et ses clients API.",
        [
            "Suivre le tableau de bord et la prochaine session",
            "Tenir à jour le profil public du dojo",
            "Planifier et publier les sessions, gérer la liste d'attente",
            "Prendre les présences, gérer l'équipe et les membres",
            "Publier des nouvelles, écrire aux familles, connecter des applications",
        ],
    ),
    "reviewer": (
        "Évaluateur",
        "Un rôle de l'organisation qui évalue uniquement les extraits de casier et décide des candidatures de bénévoles, dans le groupe Bénévoles du tableau de bord de l'organisation.",
        [
            "Se connecter en deux étapes",
            "Traiter la file des extraits de casier",
            "Valider ou refuser un document (qui est ensuite supprimé)",
            "Approuver ou refuser les candidatures de mentor et de champion",
        ],
    ),
    "organisation": (
        "Administrateur de l'organisation",
        "L'équipe et le conseil d'administration de CoderDojo Belgique. Le tableau de bord de l'organisation couvre la communication, le site public, les distinctions, les demandes liées à la vie privée, les personnes et la sécurité ; l'admin Django ne sert qu'aux interventions techniques, sur demande.",
        [
            "Campagnes e-mail, segments, parcours automatiques et modèles",
            "Suivre la file d'attente des e-mails",
            "Promotions, sponsors et distinctions",
            "Demandes liées à la vie privée, personnes et rôles, politique de connexion",
            "Journal d'audit et accès limité dans le temps à l'admin Django",
        ],
    ),
}

STEPS = {
    "parent": {
        "home": (
            "Découvrir CoderDojo",
            "Un parent arrive sur la page d'accueil. La recherche de dojos et le carrousel des prochaines sessions sont là tout de suite, sans compte.",
        ),
        "finder": (
            "Trouver un dojo près de chez vous",
            "La recherche classe les dojos selon la distance depuis une adresse tapée, la position du navigateur ou (connecté) le code postal de la famille.",
        ),
        "dojo": (
            "La page d'un dojo",
            "Chaque dojo a sa page avec ses langues, ses prochaines sessions, son équipe, ses nouvelles et les parcours d'apprentissage qu'il propose.",
        ),
        "events": (
            "Parcourir les sessions",
            "Toutes les prochaines sessions, filtrables par région, langue, âge et parcours d'apprentissage.",
        ),
        "event-full": (
            "Une session complète",
            "Quand une session est complète, les familles peuvent encore s'inscrire sur la liste d'attente ; elles avancent automatiquement quand une place se libère.",
        ),
        "signup": (
            "Créer un compte famille",
            "Inscription en libre-service : les coordonnées du parent, une ligne par enfant (d'autres avec « Ajouter un enfant »), la langue des e-mails et des consentements facultatifs. Aucune approbation nécessaire.",
        ),
        "account": (
            "La page du compte de la famille",
            "Après la connexion, la page du compte montre les coordonnées du parent (modifiables sur place), chaque enfant, ses places à venir (et sa position sur la liste d'attente) et des liens vers les préférences e-mail, la sécurité et la vie privée.",
        ),
        "child": (
            "La page d'un enfant",
            "Par enfant : coordonnées, ceinture, badges, sessions suivies et à venir, et s'il a son propre compte.",
        ),
        "event": ("Choisir une session", "Le parent ouvre une session du dojo d'attache de l'enfant."),
        "pick-children": (
            "Choisir quels enfants participent",
            "La page d'inscription liste les enfants de la famille ; ceux déjà inscrits sont indiqués.",
        ),
        "picked": ("Confirmer", "Cochez les enfants et confirmez."),
        "confirmed": (
            "Inscrit",
            "La place est confirmée immédiatement (ou l'enfant passe sur la liste d'attente) et un e-mail de confirmation est mis en file d'envoi.",
        ),
        "mail": (
            "L'e-mail de confirmation",
            "La confirmation arrive dans la langue choisie par le parent (ici le néerlandais). Pendant le développement, chaque e-mail aboutit dans Mailpit.",
        ),
        "mail-prefs": (
            "Préférences e-mail",
            "Le parent choisit les types d'e-mails qu'il reçoit, coupe les nouvelles d'un dojo, et donne ou retire son consentement par enfant.",
        ),
        "security": (
            "Sécurité de connexion",
            "Connexion en deux étapes facultative (application d'authentification, passkeys, codes de secours), ou liens de connexion au lieu d'un mot de passe.",
        ),
        "delete": (
            "Vie privée : télécharger ou supprimer",
            "Depuis la page du compte, la famille télécharge toutes ses données, ou supprime le compte après confirmation avec le mot de passe.",
        ),
    },
    "ninja": {
        "login": (
            "Se connecter avec son propre compte",
            "Un parent peut donner à un enfant (7–17 ans) son propre compte, avec un mot de passe ou des liens de connexion (la connexion en deux étapes est aussi possible). L'enfant se connecte avec le nom d'utilisateur reçu par le parent.",
        ),
        "me": (
            "Mes ceintures, badges et mon historique",
            "Le ninja voit sa ceinture actuelle et qui l'a décernée, ses badges (avec la progression vers le prochain bracelet) et chaque session à laquelle il a participé. Il peut regarder, pas modifier : ses données restent chez le parent (seul son avatar, choisi parmi les avatars standard, il le change lui-même).",
        ),
        "pathway": (
            "Découvrir un parcours d'apprentissage",
            "Les parcours (Scratch, Python, développement web, ...) montrent les étapes et projets qu'un ninja peut réaliser au dojo.",
        ),
        "event": ("Trouver la prochaine session", "Le ninja parcourt les sessions comme tout le monde ..."),
        "signup": (
            "... et s'inscrit lui-même",
            "Avec son propre compte, un ninja ne peut inscrire que lui-même. Le parent reçoit toujours l'e-mail de confirmation.",
        ),
        "done": (
            "Place confirmée",
            "La place est confirmée et apparaît sur la page du ninja et sur celle du compte du parent, où chacun peut l'annuler.",
        ),
        "security": (
            "Sa propre sécurité de connexion",
            "Le compte d'un ninja a les mêmes options de connexion que celui d'un adulte, connexion en deux étapes comprise. Le parent est averti de chaque changement.",
        ),
    },
    "volunteer": {
        "register": (
            "Devenir bénévole",
            "La page d'inscription présente les possibilités : un compte famille, aider dans un dojo comme mentor, ou lancer un dojo comme champion. Les bénévoles utilisent d'abord un compte ordinaire.",
        ),
        "apply-mentor": (
            "Poser sa candidature comme mentor",
            "Une fois connecté, tout adulte peut poser sa candidature comme mentor : éventuellement avec un dojo, ses compétences et ses disponibilités, en acceptant l'extrait de casier judiciaire. L'approbation comme mentor vaut une fois par compte, pas par dojo.",
        ),
        "apply-champion": (
            "Ou lancer un dojo",
            "Lancer un dojo, c'est la candidature de champion : région, lieu proposé et horaire. Un champion approuvé crée lui-même son dojo.",
        ),
        "check-requested": (
            "L'extrait de casier est demandé",
            "Après la candidature, un évaluateur demande l'extrait de casier judiciaire (modèle 2). La page du compte et un lien envoyé par e-mail mènent tous deux à l'envoi du document.",
        ),
        "upload": (
            "Envoyer le document",
            "Le document est conservé en privé (pas d'URL publique), seuls les évaluateurs le voient, et il est supprimé dès qu'ils décident : seule la décision est conservée.",
        ),
        "waiting": (
            "En attente d'évaluation",
            "Une fois envoyé, le compte indique que l'extrait attend un évaluateur. Les évaluateurs reçoivent un e-mail quotidien tant que des documents attendent.",
        ),
        "landing": (
            "Un mentor approuvé se connecte",
            "Une fois approuvé et dans l'équipe d'un dojo, la connexion mène directement à l'espace de gestion du dojo. Le sélecteur en haut de la barre latérale liste chaque dojo où il aide.",
        ),
        "events": (
            "Les sessions du dojo",
            "Les mentors voient et gèrent les sessions du dojo : publier, clôturer les inscriptions, rouvrir.",
        ),
        "event": (
            "Une session",
            "Les données, le statut, l'équipe et les parcours d'apprentissage de la session, modifiables sur place, plus un lien pour prendre les présences.",
        ),
        "attendance": (
            "Prendre les présences à l'entrée",
            "Le jour même, le mentor indique chaque enfant présent ou absent (htmx, sans recharger la page). Chaque ligne montre la ceinture de l'enfant, sa régularité et « En visite » pour les enfants d'un autre dojo ; l'équipe de la session figure aussi, pour l'assurance.",
        ),
        "marked": (
            "Présent",
            "Un clic indique un enfant présent et met à jour le compteur « N sur M présents ». Les badges de palier (bracelets) suivent automatiquement les présences.",
        ),
        "belt": (
            "Décerner une ceinture",
            "Les mentors décernent ceintures et badges ponctuels depuis la même liste. L'historique des ceintures ne fait que s'allonger et conserve qui l'a décernée et à quel titre.",
        ),
        "team": (
            "L'équipe du dojo",
            "Chaque mentor actif peut accepter les demandes pour rejoindre l'équipe, ajouter des mentors approuvés et promouvoir un ninja jeune mentor.",
        ),
        "join": (
            "Rejoindre un autre dojo",
            "Un mentor approuvé peut demander à rejoindre l'équipe de n'importe quel dojo depuis sa page publique ; l'équipe accepte ou refuse.",
        ),
    },
    "champion": {
        "dashboard": (
            "Le tableau de bord du dojo",
            "La page d'accueil du champion : les présences de la prochaine session, une bannière si le dojo n'est pas actif, et un rappel après six mois sans session.",
        ),
        "settings": (
            "Paramètres du dojo",
            "En haut, le statut du dojo : seul le champion lance le dojo, le met en sommeil ou l'archive (jamais avec des sessions ouvertes) et le rouvre. En dessous, tout ce qui figure sur la page publique du dojo : nom, description dans chaque langue du dojo, icône, adresse (géolocalisée à l'enregistrement), coordonnées et parcours d'apprentissage.",
        ),
        "events": (
            "Sessions",
            "Toutes les sessions du dojo avec leur statut (brouillon, ouverte, clôturée) et l'étape suivante en un clic.",
        ),
        "new-event": (
            "Planifier une nouvelle session",
            "Une nouvelle session : date et heures (notation belge), places, âges, public (p. ex. une session pour filles), une bannière de la bibliothèque d'images ou envoyée, l'équipe et les parcours d'apprentissage. Elle commence en brouillon ; la publier ouvre les inscriptions et les familles reçoivent l'e-mail des nouvelles sessions.",
        ),
        "event": (
            "Une session complète avec liste d'attente",
            "La page de la session montre les places prises et la liste d'attente ; quand une famille annule, le premier enfant en attente avance et sa famille reçoit un e-mail.",
        ),
        "attendance": (
            "Présences avec informations de santé",
            "La liste de présences du champion montre aussi les allergies et informations de santé de la famille, uniquement pour les enfants avec une place confirmée, et chaque consultation est enregistrée dans le journal d'audit.",
        ),
        "team": (
            "Gérer l'équipe",
            "Accepter les demandes pour rejoindre l'équipe, ajouter des mentors, promouvoir des jeunes mentors, et transmettre le rôle de champion à un mentor actif.",
        ),
        "members": (
            "Membres",
            "Les enfants dont c'est le dojo d'attache, avec un bouton pour en promouvoir un jeune mentor.",
        ),
        "updates": ("Nouvelles", "De courts messages « De ce dojo » sur la page publique du dojo."),
        "mail": (
            "E-mails aux familles",
            "Le champion écrit aux familles du dojo (ou à sa propre équipe), quelques fois par mois au plus. L'équipe voit des nombres, jamais les adresses des familles.",
        ),
        "mail-new": (
            "Écrire un e-mail",
            "Objet et message dans chaque langue du dojo et un public préparé (toutes les familles, l'âge ou la ceinture d'un enfant, ...). Les familles répondent directement à l'adresse du dojo et peuvent couper les nouvelles d'un seul dojo.",
        ),
        "api": (
            "Clients API",
            "Pour les applications qui travaillent pour le dojo (p. ex. scanner les enfants à l'entrée) : OAuth 2.0 client credentials avec des droits sur les présences, réservé au champion.",
        ),
    },
    "reviewer": {
        "login-2fa": (
            "Connexion en deux étapes",
            "Les évaluateurs voient des extraits de casier judiciaire ; ce compte se connecte donc après le mot de passe avec un code d'une application d'authentification (passkeys et codes de secours fonctionnent aussi). L'organisation peut l'imposer par rôle.",
        ),
        "checks": (
            "Extraits de casier",
            "L'évaluateur arrive dans le groupe Bénévoles, les seules pages que ce rôle ouvre. La file : documents à évaluer, extraits en attente d'un document, et extraits expirés ou bientôt expirés.",
        ),
        "check": (
            "Évaluer un extrait",
            "L'extrait d'une personne : téléchargez le document, puis validez-le ou refusez-le. Les deux décisions suppriment le document immédiatement ; seuls la décision, l'évaluateur et la date d'expiration sont conservés. L'ouverture de cette page est enregistrée dans le journal d'audit.",
        ),
        "applications": (
            "Candidatures",
            "Candidatures de mentor et de champion, avec l'état de l'extrait de casier de chaque candidat.",
        ),
        "application": (
            "Décider d'une candidature",
            "Avec un extrait valable, l'évaluateur approuve (un mentor approuvé peut alors rejoindre des dojos, un champion en créer un) ou refuse. Personne ne décide de sa propre candidature ou de son propre extrait.",
        ),
    },
    "organisation": {
        "campaigns": (
            "Campagnes",
            "La connexion (en deux étapes) mène au tableau de bord de l'organisation. La barre latérale regroupe les pages par domaine (Communication, Site public, Ninjas, Comptes, Organisation), et le sélecteur liste aussi les événements propres à l'organisation (Coolest Projects, CoderDojo Girlz). Les campagnes sont des envois uniques, avec leurs résultats (en file, envoyés, revenus, bloqués).",
        ),
        "campaign": (
            "Une campagne",
            "Modifier un brouillon, le prévisualiser dans chaque langue, voir le nombre de destinataires et un échantillon, s'envoyer un test, puis lancer (maintenant ou planifié). Le public est figé au lancement.",
        ),
        "segments": ("Segments", "Des publics décrits sans code, avec des nombres en direct."),
        "segment": (
            "Le constructeur de segments",
            "Des groupes de règles sur les comptes ou sur « le même enfant » (âge, genre, ceinture, dojo d'attache, engagement, distance à un dojo, ...), combinés par ET ou OU et imbriqués. Les règles sur les enfants n'atteignent que les parents qui ont donné leur consentement.",
        ),
        "journeys": (
            "Parcours automatiques",
            "Des campagnes permanentes qui tournent chaque jour, p. ex. un e-mail « tu nous manques » la semaine où un enfant risque de décrocher.",
        ),
        "templates": (
            "Modèles d'e-mail",
            "Chaque e-mail que le site envoie, en anglais, néerlandais et français, et ce qui l'utilise.",
        ),
        "queue": (
            "File d'attente des e-mails",
            "E-mails en attente et en échec, retours et adresses bloquées, avec un avertissement quand les workers semblent arrêtés.",
        ),
        "promotions": (
            "Promotions",
            "Mettre en avant des événements (p. ex. Coolest Projects) sur la page d'accueil et ailleurs, pour une période donnée.",
        ),
        "sponsors": ("Sponsors", "« Rendu possible par » sur la page d'accueil."),
        "awards": (
            "Distinctions",
            "Seule l'organisation crée les badges : des badges ponctuels que les dojos décernent, et des badges de palier liés aux présences (qui peuvent donner une ceinture).",
        ),
        "privacy": (
            "Demandes liées à la vie privée",
            "Retrouver n'importe quel compte pour en télécharger les données, changer son adresse e-mail ou le supprimer, et voir les comptes que la rétention retient.",
        ),
        "people": (
            "Personnes",
            "Qui a quel rôle à l'organisation (administrateur, conseil, évaluateur), les invitations pour les personnes sans compte, et les accès ouverts à l'admin Django.",
        ),
        "security": (
            "Politique de connexion",
            "Quels rôles doivent se connecter en deux étapes ou avec une passkey, à partir de quelle date ; et désactiver la connexion en deux étapes de quelqu'un qui a perdu son téléphone.",
        ),
        "audit": (
            "Journal d'audit",
            "Qui a modifié quoi, et qui a consulté des données sensibles. En lecture seule ; les champs de santé et de sécurité restent masqués.",
        ),
        "django-admin": (
            "L'admin Django sur demande",
            "L'admin Django ne sert qu'aux interventions techniques : un rôle de l'organisation la demande avec un motif et son mot de passe, pour 12 heures, et les autres administrateurs sont avertis.",
        ),
    },
}
