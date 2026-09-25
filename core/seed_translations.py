"""Dutch and French versions of the demo seed texts (the seeders write
English), used by `manage.py seed_content_languages` to make the seeded
site multilingual the way a real one would be (DATA_MODEL.md §19).
Keyed by the exact English text a seeder writes; values are (nl-be, fr-be).
Dutch uses "je", French "vous" (CLAUDE.md, "i18n")."""

NL, FR, EN = "nl-be", "fr-be", "en-us"

T = {
    # --- pathways ---------------------------------------------------------------
    "Scratch": ("Scratch", "Scratch"),
    "Drag-and-drop blocks and real games from your very first Saturday — no experience needed.": (
        "Blokjes slepen en echte spelletjes maken vanaf je allereerste zaterdag, zonder ervaring.",
        "Des blocs à glisser et de vrais jeux dès votre tout premier samedi, sans expérience."),
    ("Scratch is where almost every ninja starts. Instead of typing code, you snap together "
     "coloured blocks to make a character move, react and keep score — so you're building a real "
     "game or animation in your first session, mistakes and all. It's the same block-based approach "
     "used in schools everywhere, just with a mentor next to you and a room full of other kids "
     "building their own thing at the same time."): (
        "Bijna elke ninja begint met Scratch. In plaats van code te typen, klik je gekleurde blokjes aan "
        "elkaar om een figuurtje te laten bewegen, reageren en punten te laten tellen. Zo bouw je al in je "
        "eerste sessie een echt spel of een animatie, met fouten en al. Het is dezelfde aanpak met blokjes "
        "als op school, alleen met een mentor naast je en een zaal vol andere kinderen die tegelijk hun eigen "
        "ding bouwen.",
        "Presque tous les ninjas commencent par Scratch. Au lieu de taper du code, on assemble des blocs "
        "colorés pour faire bouger un personnage, le faire réagir et compter les points : on construit donc "
        "un vrai jeu ou une animation dès la première session, erreurs comprises. C'est la même approche par "
        "blocs qu'à l'école, mais avec un mentor à côté de soi et une salle pleine d'autres enfants qui "
        "construisent leur propre projet en même temps."),
    "Pick a starter project": ("Kies een startproject", "Choisir un projet de départ"),
    "Mentors bring a few ready-to-remix projects along for anyone who wants a running start.": (
        "Mentors brengen een paar projecten mee om te remixen, voor wie snel wil starten.",
        "Les mentors apportent quelques projets prêts à remixer pour ceux qui veulent démarrer vite."),
    "Make it your own": ("Maak het van jezelf", "Se l'approprier"),
    "Change the art, the rules, the story — it's not finished until you've broken something on purpose.": (
        "Verander de tekeningen, de regels, het verhaal: het is pas af als je iets expres kapotgemaakt hebt.",
        "Changez les dessins, les règles, l'histoire : ce n'est pas fini tant qu'on n'a pas cassé quelque chose exprès."),
    "Show the group": ("Toon het aan de groep", "Montrer au groupe"),
    "Most sessions end with a few kids sharing their screen — no pressure, just show-and-tell.": (
        "De meeste sessies eindigen met een paar kinderen die hun scherm tonen, zonder druk.",
        "La plupart des sessions se terminent par quelques enfants qui montrent leur écran, sans pression."),
    "A platformer game": ("Een platformspel", "Un jeu de plateforme"),
    "Design your own levels, add a jumping hero, and make it a little harder to beat with each try.": (
        "Ontwerp je eigen levels, voeg een springende held toe en maak het bij elke poging wat moeilijker.",
        "Concevez vos propres niveaux, ajoutez un héros qui saute et rendez le jeu un peu plus difficile à chaque essai."),
    "A quiz game": ("Een quizspel", "Un jeu de quiz"),
    "Write your own questions and keep score when a friend picks up the controls.": (
        "Schrijf je eigen vragen en hou de score bij als een vriend mag spelen.",
        "Écrivez vos propres questions et comptez les points quand un ami prend les commandes."),
    "An animated card": ("Een bewegende kaart", "Une carte animée"),
    "Combine sprites, sound and a bit of logic into something you can actually send someone.": (
        "Combineer figuurtjes, geluid en wat logica tot iets dat je echt naar iemand kunt sturen.",
        "Combinez des personnages, du son et un peu de logique pour créer quelque chose à envoyer à quelqu'un."),
    "How long does the Scratch pathway take?": ("Hoe lang duurt het leertraject Scratch?", "Combien de temps dure le parcours Scratch ?"),
    "There's no fixed length — most kids spend a few sessions here before trying Python or Web, and some stay much longer. It's fine either way.": (
        "Er is geen vaste duur. De meeste kinderen blijven hier een paar sessies voor ze Python of Web proberen, sommigen veel langer. Allebei prima.",
        "Il n'y a pas de durée fixe : la plupart des enfants y passent quelques sessions avant d'essayer Python ou le Web, certains beaucoup plus longtemps. Les deux sont très bien."),
    "My child already knows Scratch — should they still start here?": (
        "Mijn kind kent Scratch al. Moet het toch hier beginnen?",
        "Mon enfant connaît déjà Scratch : doit-il quand même commencer ici ?"),
    "Not necessarily — a mentor can place them straight into Python or Web on their very first visit.": (
        "Niet per se: een mentor kan je kind bij het eerste bezoek meteen met Python of Web laten starten.",
        "Pas forcément : un mentor peut l'orienter directement vers Python ou le Web dès sa première visite."),
    "Do they need to install anything at home?": ("Moet er thuis iets geïnstalleerd worden?", "Faut-il installer quelque chose à la maison ?"),
    "No — Scratch runs in the browser on the dojo's own laptops, so there's nothing to install beforehand.": (
        "Nee, Scratch werkt in de browser op de laptops van de dojo, dus je hoeft vooraf niets te installeren.",
        "Non : Scratch fonctionne dans le navigateur sur les ordinateurs du dojo, il n'y a donc rien à installer."),

    "Python": ("Python", "Python"),
    "Trade the blocks for real code and build your first text-based games and programs.": (
        "Ruil de blokjes in voor echte code en bouw je eerste spelletjes en programma's in tekst.",
        "Remplacez les blocs par du vrai code et créez vos premiers jeux et programmes en texte."),
    ("Python is usually the next step after Scratch, though plenty of kids start here directly. "
     "You're writing actual lines of code in a real, widely-used programming language — the same one "
     "used for data science, web backends and much more — but the projects stay small and fun: a "
     "bot that quizzes your friends, a game of hangman, a program that always wins at rock-paper-scissors "
     "(or always loses, if that's funnier)."): (
        "Python is meestal de volgende stap na Scratch, al beginnen veel kinderen hier meteen. Je schrijft "
        "echte regels code in een echte, veelgebruikte programmeertaal (dezelfde als voor datawetenschap, "
        "websites en nog veel meer), maar de projecten blijven klein en leuk: een bot die je vrienden "
        "overhoort, galgje, of een programma dat altijd wint bij blad-steen-schaar (of altijd verliest, als "
        "dat grappiger is).",
        "Python est souvent l'étape suivante après Scratch, même si beaucoup d'enfants commencent "
        "directement ici. On écrit de vraies lignes de code dans un vrai langage très utilisé (le même qu'en "
        "science des données, pour les sites web et bien plus), mais les projets restent petits et amusants : "
        "un robot qui interroge vos amis, un pendu, un programme qui gagne toujours à pierre-feuille-ciseaux "
        "(ou qui perd toujours, si c'est plus drôle)."),
    "Start from a template": ("Begin van een sjabloon", "Partir d'un modèle"),
    "A short starter script gets everyone past the blank-page problem in the first five minutes.": (
        "Een kort startscript helpt iedereen in de eerste vijf minuten voorbij het lege blad.",
        "Un petit script de départ évite à chacun la page blanche dans les cinq premières minutes."),
    "Add your own twist": ("Voeg je eigen draai toe", "Ajouter sa touche"),
    "New questions, new rules, new random events — small changes that make the program feel like yours.": (
        "Nieuwe vragen, nieuwe regels, nieuwe toevallige gebeurtenissen: kleine wijzigingen die het programma van jou maken.",
        "Nouvelles questions, nouvelles règles, nouveaux événements aléatoires : de petits changements qui rendent le programme le vôtre."),
    "Trade with a friend": ("Ruil met een vriend", "Échanger avec un ami"),
    "Swap programs with someone else and try to break each other's — it's the fastest way to find real bugs.": (
        "Wissel programma's met iemand anders en probeer elkaars programma kapot te krijgen: zo vind je het snelst echte bugs.",
        "Échangez vos programmes et essayez de faire planter celui de l'autre : c'est le moyen le plus rapide de trouver de vrais bugs."),
    "A quiz bot": ("Een quizbot", "Un robot de quiz"),
    "Write your own questions, keep score, and tell the player how they did at the end.": (
        "Schrijf je eigen vragen, hou de score bij en vertel de speler op het einde hoe hij het deed.",
        "Écrivez vos questions, comptez les points et dites au joueur comment il s'en est sorti à la fin."),
    "Hangman": ("Galgje", "Le pendu"),
    "Guess the letters, track the wrong guesses, and pick your own word list.": (
        "Raad de letters, tel de foute gokken en kies je eigen woordenlijst.",
        "Devinez les lettres, comptez les erreurs et choisissez votre propre liste de mots."),
    "Rock-paper-scissors": ("Blad-steen-schaar", "Pierre-feuille-ciseaux"),
    "Play against the computer, keep a running score, and add a few trick moves if you're feeling bold.": (
        "Speel tegen de computer, hou de score bij en voeg een paar trucs toe als je durft.",
        "Jouez contre l'ordinateur, tenez le score et ajoutez quelques coups spéciaux si vous osez."),
    "Does my child need to know Scratch first?": ("Moet mijn kind eerst Scratch kennen?", "Mon enfant doit-il d'abord connaître Scratch ?"),
    "It helps but isn't required — some kids find typed code easier to reason about than blocks.": (
        "Het helpt, maar het hoeft niet. Sommige kinderen vinden getypte code zelfs makkelijker dan blokjes.",
        "Ça aide, mais ce n'est pas obligatoire : certains enfants trouvent le code tapé plus facile à comprendre que les blocs."),
    "What do they code in?": ("Waarin programmeren ze?", "Avec quoi programment-ils ?"),
    "A browser-based Python editor, so there's nothing to install and mentors can see everyone's screen easily.": (
        "Een Python-editor in de browser, dus er hoeft niets geïnstalleerd te worden en mentors kunnen makkelijk meekijken.",
        "Un éditeur Python dans le navigateur : rien à installer, et les mentors voient facilement l'écran de chacun."),
    "What if they get a syntax error and get stuck?": ("En als ze vastlopen op een syntaxfout?", "Et s'ils bloquent sur une erreur de syntaxe ?"),
    "That's most of the session, for everyone — mentors treat error messages as the normal next step, not a wrong turn.": (
        "Dat is voor iedereen het grootste deel van de sessie. Mentors zien foutmeldingen als de normale volgende stap, niet als een vergissing.",
        "C'est la majeure partie de la session, pour tout le monde : les mentors voient les messages d'erreur comme l'étape suivante normale, pas comme une fausse route."),

    "Web Development": ("Webontwikkeling", "Développement web"),
    "Design and publish your own website with HTML, CSS and a bit of JavaScript.": (
        "Ontwerp en publiceer je eigen website met HTML, CSS en een beetje JavaScript.",
        "Concevez et publiez votre propre site web avec HTML, CSS et un peu de JavaScript."),
    ("Every website you've ever visited is built from the same three building blocks: HTML for the "
     "content, CSS for how it looks, and JavaScript for what it does when you click something. This "
     "pathway builds all three up gradually — you'll have a page with your own words and images on "
     "it in the first session, then spend later ones making it look good and adding little interactive "
     "touches."): (
        "Elke website die je ooit bezocht, is gebouwd met dezelfde drie bouwstenen: HTML voor de inhoud, CSS "
        "voor hoe het eruitziet en JavaScript voor wat er gebeurt als je ergens op klikt. Dit leertraject "
        "bouwt ze alle drie stap voor stap op: in de eerste sessie heb je al een pagina met je eigen tekst en "
        "foto's, daarna maak je ze mooi en voeg je kleine interactieve dingen toe.",
        "Chaque site que vous avez visité repose sur les trois mêmes briques : HTML pour le contenu, CSS pour "
        "l'apparence et JavaScript pour ce qui se passe quand on clique. Ce parcours les aborde toutes les "
        "trois progressivement : dès la première session, vous avez une page avec vos propres textes et "
        "images, puis vous l'embellissez et ajoutez de petites touches interactives."),
    "Write the content first": ("Schrijf eerst de inhoud", "Écrire d'abord le contenu"),
    "Headings, paragraphs and images go in before any styling — a webpage in plain HTML still works, it's just plain.": (
        "Titels, alinea's en afbeeldingen komen eerst, nog voor de opmaak. Een pagina in gewone HTML werkt ook, ze is alleen eenvoudig.",
        "Titres, paragraphes et images d'abord, avant toute mise en forme : une page en HTML simple fonctionne, elle est juste sobre."),
    "Style it with CSS": ("Maak het mooi met CSS", "La mettre en forme avec CSS"),
    "Colours, fonts and spacing turn the plain page into something that looks like a real site.": (
        "Kleuren, lettertypes en witruimte maken van de eenvoudige pagina iets dat op een echte site lijkt.",
        "Couleurs, polices et espacements transforment la page simple en un vrai site."),
    "Add one interactive touch": ("Voeg iets interactiefs toe", "Ajouter une touche interactive"),
    "A button that changes something, a simple quiz, a photo that swaps on click — small JavaScript, big satisfaction.": (
        "Een knop die iets verandert, een eenvoudige quiz, een foto die wisselt bij een klik: weinig JavaScript, veel voldoening.",
        "Un bouton qui change quelque chose, un petit quiz, une photo qui change au clic : peu de JavaScript, beaucoup de satisfaction."),
    "A personal profile page": ("Een persoonlijke profielpagina", "Une page de profil personnelle"),
    "Introduce yourself, your hobbies and your favourite things with your own layout and colours.": (
        "Stel jezelf, je hobby's en je lievelingsdingen voor met je eigen opmaak en kleuren.",
        "Présentez-vous, vos loisirs et vos choses préférées avec votre propre mise en page et vos couleurs."),
    "A photo gallery": ("Een fotogalerij", "Une galerie photo"),
    "Lay out a grid of images with captions, and make it look good on both a laptop and a phone.": (
        "Zet afbeeldingen met onderschriften in een raster, en zorg dat het er op een laptop en een gsm goed uitziet.",
        "Disposez des images avec légendes en grille, et faites en sorte que ce soit beau sur ordinateur comme sur téléphone."),
    "An interactive quiz page": ("Een interactieve quizpagina", "Une page de quiz interactive"),
    "Ask a question, check the answer with a bit of JavaScript, and reveal a result.": (
        "Stel een vraag, controleer het antwoord met wat JavaScript en toon een resultaat.",
        "Posez une question, vérifiez la réponse avec un peu de JavaScript et affichez un résultat."),
    "Do they need to know how to type well?": ("Moeten ze goed kunnen typen?", "Faut-il savoir bien taper ?"),
    "Not especially — most of a session is spent thinking through the page's structure, and mentors help with the typing-heavy bits.": (
        "Niet echt. Het grootste deel van een sessie gaat naar nadenken over de opbouw van de pagina, en mentors helpen bij het vele typwerk.",
        "Pas vraiment : on passe l'essentiel de la session à réfléchir à la structure de la page, et les mentors aident pour les parties à taper."),
    "Will their website be online for real?": ("Komt hun website echt online?", "Leur site sera-t-il vraiment en ligne ?"),
    "Not by default — pages are built and viewed locally during the session, though a mentor can point interested families toward free hosting afterwards.": (
        "Niet standaard: de pagina's worden tijdens de sessie lokaal gemaakt en bekeken, maar een mentor kan geïnteresseerde gezinnen daarna gratis hosting aanraden.",
        "Pas par défaut : les pages sont créées et consultées en local pendant la session, mais un mentor peut ensuite orienter les familles intéressées vers un hébergement gratuit."),
    "Is this the same as app development?": ("Is dit hetzelfde als apps maken?", "Est-ce la même chose que créer des applis ?"),
    "No — this pathway is about websites specifically. Ninjas curious about apps are usually pointed toward Python or Unity instead.": (
        "Nee, dit leertraject gaat specifiek over websites. Ninja's die apps willen maken, worden meestal naar Python of Unity doorverwezen.",
        "Non, ce parcours porte spécifiquement sur les sites web. Les ninjas curieux des applis sont plutôt orientés vers Python ou Unity."),

    "BBC micro:bit": ("BBC micro:bit", "BBC micro:bit"),
    "Code a tiny physical computer — lights, buttons and sensors you can hold in your hand.": (
        "Programmeer een piepkleine computer met lichtjes, knoppen en sensoren die je in je hand houdt.",
        "Programmez un minuscule ordinateur, avec des lumières, des boutons et des capteurs à tenir dans la main."),
    ("The micro:bit is a small, real computer with its own lights, buttons, compass and radio — and "
     "you program it with the same drag-and-drop blocks as Scratch (or Python, if you'd rather type). "
     "The difference is what happens next: you plug it in, and the code runs on an actual device you "
     "can hold, shake, wear or race against a friend's."): (
        "De micro:bit is een kleine, echte computer met eigen lichtjes, knoppen, kompas en radio. Je "
        "programmeert hem met dezelfde blokjes als in Scratch (of met Python, als je liever typt). Het "
        "verschil zit in wat daarna gebeurt: je steekt hem in, en je code draait op een echt toestel dat je "
        "kunt vasthouden, schudden, dragen of laten racen tegen dat van een vriend.",
        "Le micro:bit est un petit ordinateur bien réel, avec ses propres lumières, boutons, boussole et "
        "radio, que l'on programme avec les mêmes blocs que Scratch (ou en Python, si on préfère taper). La "
        "différence, c'est la suite : on le branche, et le code tourne sur un vrai appareil qu'on peut tenir, "
        "secouer, porter ou faire affronter celui d'un ami."),
    "Design on screen first": ("Eerst ontwerpen op het scherm", "Concevoir d'abord à l'écran"),
    "Every project starts in the browser-based editor, so you can test the logic before it touches a real device.": (
        "Elk project begint in de editor in de browser, zodat je de logica kunt testen voor het op een echt toestel komt.",
        "Chaque projet commence dans l'éditeur du navigateur, pour tester la logique avant de passer à un vrai appareil."),
    "Flash it to a micro:bit": ("Zet het op een micro:bit", "Le transférer sur un micro:bit"),
    "One click sends your code onto the board — plugged in over USB, no extra setup needed.": (
        "Met één klik staat je code op het bordje, via USB, zonder extra instellingen.",
        "Un clic suffit pour envoyer le code sur la carte, branchée en USB, sans autre réglage."),
    "Test it for real": ("Test het echt", "Le tester pour de vrai"),
    "Shake it, press its buttons, walk around with it — physical testing finds things the simulator can't.": (
        "Schud ermee, druk op de knoppen, wandel ermee rond: echt testen vindt dingen die de simulator mist.",
        "Secouez-le, appuyez sur ses boutons, promenez-vous avec : le test réel trouve ce que le simulateur rate."),
    "A reaction-time game": ("Een reactiespel", "Un jeu de réflexes"),
    "Light up randomly and see how fast a friend can press the button.": (
        "Laat lichtjes toevallig oplichten en kijk hoe snel een vriend op de knop drukt.",
        "Allumez des lumières au hasard et voyez à quelle vitesse un ami appuie sur le bouton."),
    "A step counter": ("Een stappenteller", "Un podomètre"),
    "Use the built-in accelerometer to count steps and show the total on the LED display.": (
        "Gebruik de ingebouwde versnellingsmeter om stappen te tellen en toon het totaal op het ledscherm.",
        "Utilisez l'accéléromètre intégré pour compter les pas et afficher le total sur l'écran à LED."),
    "Tilt rock-paper-scissors": ("Blad-steen-schaar door te schudden", "Pierre-feuille-ciseaux en secouant"),
    "Shake to pick a move and use radio to play against a friend's micro:bit.": (
        "Schud om een zet te kiezen en speel via de radio tegen de micro:bit van een vriend.",
        "Secouez pour choisir un coup et jouez par radio contre le micro:bit d'un ami."),
    "Do we need to bring our own micro:bit?": ("Moeten we een eigen micro:bit meebrengen?", "Faut-il apporter son propre micro:bit ?"),
    "No — most dojos keep a set of boards and USB cables on hand to borrow for the session.": (
        "Nee, de meeste dojo's hebben een set bordjes en USB-kabels om tijdens de sessie te lenen.",
        "Non : la plupart des dojos ont des cartes et des câbles USB à prêter pendant la session."),
    "Is this just Scratch on a different screen?": ("Is dit gewoon Scratch op een ander scherm?", "Est-ce juste Scratch sur un autre écran ?"),
    "It starts similarly (drag-and-drop blocks) but the moment your code controls a physical light or button, it feels very different.": (
        "Het begint gelijkaardig (blokjes slepen), maar zodra je code een echt lichtje of een knop bestuurt, voelt het heel anders.",
        "Ça commence de la même façon (des blocs à glisser), mais dès que votre code contrôle une vraie lumière ou un bouton, c'est très différent."),
    "Can my child take their project home?": ("Mag mijn kind het project mee naar huis nemen?", "Mon enfant peut-il emporter son projet ?"),
    "The code, yes — projects save to the browser and export as a file. The physical micro:bit itself usually stays with the dojo's kit.": (
        "De code wel: projecten worden in de browser bewaard en kunnen als bestand gedownload worden. De micro:bit zelf blijft meestal bij de dojo.",
        "Le code, oui : les projets sont enregistrés dans le navigateur et s'exportent en fichier. Le micro:bit lui-même reste en général au dojo."),

    "Raspberry Pi (physical computing)": ("Raspberry Pi (elektronica)", "Raspberry Pi (électronique)"),
    "Wire up real circuits and control them with code — lights, sensors, buzzers and more.": (
        "Bouw echte schakelingen en bestuur ze met code: lichtjes, sensoren, zoemers en meer.",
        "Câblez de vrais circuits et contrôlez-les avec du code : lumières, capteurs, buzzers et plus."),
    ("This is where code meets a breadboard. Using a Raspberry Pi's GPIO pins, you'll wire up real "
     "components — LEDs, buttons, buzzers, sensors — and write Python to control them. It's slower and "
     "more hands-on than screen-only pathways (there's wiring to get right, not just code), which is "
     "exactly what makes it satisfying: a program that makes a physical light blink on command."): (
        "Hier komen code en breadboard samen. Met de GPIO-pinnen van een Raspberry Pi sluit je echte "
        "onderdelen aan (leds, knoppen, zoemers, sensoren) en schrijf je Python om ze te besturen. Het gaat "
        "trager en is meer handwerk dan leertrajecten op het scherm (de bedrading moet ook kloppen, niet "
        "alleen de code), en net dat geeft zoveel voldoening: een programma dat op commando een echt lichtje "
        "laat knipperen.",
        "Ici, le code rencontre la plaque d'essai. Grâce aux broches GPIO d'un Raspberry Pi, vous branchez de "
        "vrais composants (LED, boutons, buzzers, capteurs) et écrivez du Python pour les contrôler. C'est "
        "plus lent et plus manuel que les parcours sur écran (le câblage doit être juste, pas seulement le "
        "code), et c'est justement ce qui rend la chose si satisfaisante : un programme qui fait clignoter une "
        "vraie lumière sur commande."),
    "Wire the circuit": ("Bouw de schakeling", "Câbler le circuit"),
    "Follow a diagram to connect components to the right GPIO pins — a mentor checks the wiring before anything gets powered on.": (
        "Volg een schema om onderdelen op de juiste GPIO-pinnen aan te sluiten. Een mentor controleert de bedrading voor er stroom op komt.",
        "Suivez un schéma pour brancher les composants sur les bonnes broches GPIO : un mentor vérifie le câblage avant la mise sous tension."),
    "Write the code": ("Schrijf de code", "Écrire le code"),
    "Python controls the circuit: turning pins on and off, or reading a sensor's value.": (
        "Python bestuurt de schakeling: pinnen aan- en uitzetten of de waarde van een sensor uitlezen.",
        "Python contrôle le circuit : allumer et éteindre des broches, ou lire la valeur d'un capteur."),
    "Test, then debug the wiring or the code": ("Test, en zoek dan de fout in de bedrading of de code", "Tester, puis déboguer le câblage ou le code"),
    "If it doesn't work, it's usually one or the other — working out which is most of the skill here.": (
        "Als het niet werkt, ligt het meestal aan het ene of het andere. Uitzoeken welk van de twee is hier de grootste vaardigheid.",
        "Si ça ne marche pas, c'est généralement l'un ou l'autre : trouver lequel, c'est l'essentiel du savoir-faire ici."),
    "A traffic light sequence": ("Verkeerslichten", "Des feux de circulation"),
    "Wire three LEDs and time a proper red-amber-green-amber sequence in code.": (
        "Sluit drie leds aan en programmeer een echte volgorde rood-oranje-groen-oranje.",
        "Branchez trois LED et programmez une vraie séquence rouge-orange-vert-orange."),
    "A burglar alarm": ("Een inbraakalarm", "Une alarme antivol"),
    "A motion sensor triggers a buzzer and a flashing light — with a keypad code to disarm it.": (
        "Een bewegingssensor laat een zoemer en een knipperlicht afgaan, met een code om het alarm uit te zetten.",
        "Un capteur de mouvement déclenche un buzzer et une lumière clignotante, avec un code pour le désactiver."),
    "A mini weather station": ("Een mini-weerstation", "Une mini station météo"),
    "Read temperature and humidity from a sensor and log or display the results.": (
        "Lees temperatuur en vochtigheid uit een sensor en hou de resultaten bij of toon ze.",
        "Lisez la température et l'humidité d'un capteur, puis enregistrez ou affichez les résultats."),
    "Is prior coding experience required?": ("Is programmeerervaring nodig?", "Faut-il déjà savoir programmer ?"),
    "Basic Python (variables, loops, functions) helps a lot — mentors usually suggest finishing a few Python sessions first.": (
        "Wat basis-Python (variabelen, lussen, functies) helpt veel. Mentors raden meestal aan om eerst een paar Python-sessies te volgen.",
        "Des bases en Python (variables, boucles, fonctions) aident beaucoup : les mentors conseillent souvent de suivre d'abord quelques sessions Python."),
    "What if we let out the magic smoke?": ("En als er toch rook uit komt?", "Et si on fait sortir la fumée magique ?"),
    "It happens — mentors check wiring before power-on specifically to keep this rare, and the dojo keeps spare components on hand.": (
        "Dat gebeurt. Mentors controleren de bedrading voor de stroom aangaat net om dat zeldzaam te houden, en de dojo heeft reserveonderdelen.",
        "Ça arrive : les mentors vérifient le câblage avant la mise sous tension justement pour que ce soit rare, et le dojo a des composants de rechange."),
    "Do we need our own Raspberry Pi?": ("Hebben we een eigen Raspberry Pi nodig?", "Faut-il son propre Raspberry Pi ?"),
    "No — the dojo's kit includes boards, breadboards, jumper wires and a starter set of components to borrow for the session.": (
        "Nee, de dojo heeft bordjes, breadboards, draadjes en een startset onderdelen om tijdens de sessie te lenen.",
        "Non : le kit du dojo comprend des cartes, des plaques d'essai, des câbles et un jeu de composants à emprunter pendant la session."),

    "3D Printing": ("3D-printen", "Impression 3D"),
    "Design something in 3D on screen, then watch it actually get printed.": (
        "Ontwerp iets in 3D op het scherm en kijk hoe het echt geprint wordt.",
        "Concevez un objet en 3D à l'écran, puis regardez-le s'imprimer pour de vrai."),
    ("You design a real, physical object — a keyring, a phone stand, a custom cookie cutter — using "
     "simple browser-based 3D modelling, then send it to a 3D printer and watch it get built up layer "
     "by layer. It's less about coding and more about spatial thinking and iteration: your first version "
     "rarely fits or works quite right, and fixing that is the whole point."): (
        "Je ontwerpt een echt voorwerp (een sleutelhanger, een gsm-houder, een eigen koekjesvorm) met "
        "eenvoudig 3D-modelleren in de browser, stuurt het naar een 3D-printer en kijkt hoe het laag per laag "
        "opgebouwd wordt. Het gaat minder over programmeren en meer over ruimtelijk denken en verbeteren: je "
        "eerste versie past of werkt zelden meteen, en dat oplossen is net de bedoeling.",
        "Vous concevez un vrai objet (un porte-clés, un support de téléphone, un emporte-pièce sur mesure) avec "
        "un outil de modélisation 3D simple dans le navigateur, puis vous l'envoyez à une imprimante 3D et le "
        "regardez se construire couche par couche. Il s'agit moins de code que de vision dans l'espace et "
        "d'amélioration : la première version tombe rarement juste, et la corriger est tout l'intérêt."),
    "Sketch the idea": ("Schets het idee", "Esquisser l'idée"),
    "A quick pencil sketch with rough measurements saves a lot of on-screen guessing later.": (
        "Een snelle potloodschets met ruwe afmetingen bespaart later veel gegok op het scherm.",
        "Un rapide croquis au crayon avec des mesures approximatives évite beaucoup de tâtonnements à l'écran."),
    "Model it in the browser": ("Modelleer het in de browser", "Le modéliser dans le navigateur"),
    "Simple shapes are combined, stretched and cut to build up the final design.": (
        "Eenvoudige vormen worden gecombineerd, uitgerekt en versneden tot het uiteindelijke ontwerp.",
        "Des formes simples sont combinées, étirées et découpées pour construire le modèle final."),
    "Print, check, and refine": ("Printen, controleren en verbeteren", "Imprimer, vérifier et améliorer"),
    "First prints rarely come out perfect — measuring what's wrong and adjusting the model is where most of the learning happens.": (
        "Een eerste print is zelden perfect. Meten wat er mis is en het model aanpassen, daar leer je het meest.",
        "Les premières impressions sont rarement parfaites : mesurer ce qui cloche et ajuster le modèle, c'est là qu'on apprend le plus."),
    "A keyring": ("Een sleutelhanger", "Un porte-clés"),
    "A small, quick-printing first project — a name, an initial, or a simple shape.": (
        "Een klein eerste project dat snel geprint is: een naam, een initiaal of een eenvoudige vorm.",
        "Un petit premier projet rapide à imprimer : un prénom, une initiale ou une forme simple."),
    "A phone stand": ("Een gsm-houder", "Un support de téléphone"),
    "Design angled supports that actually hold a phone up without tipping over.": (
        "Ontwerp schuine steunen die een gsm echt rechtop houden zonder om te vallen.",
        "Concevez des appuis inclinés qui tiennent vraiment un téléphone sans qu'il bascule."),
    "A custom cookie cutter": ("Een eigen koekjesvorm", "Un emporte-pièce sur mesure"),
    "Trace or design a shape, then think through wall thickness so it holds together and actually cuts.": (
        "Teken of ontwerp een vorm en denk na over de wanddikte, zodat hij stevig is en echt snijdt.",
        "Tracez ou dessinez une forme, puis réfléchissez à l'épaisseur des parois pour qu'il tienne et découpe vraiment."),
    "How long does a print take?": ("Hoe lang duurt een print?", "Combien de temps dure une impression ?"),
    "Small projects can print during the session; bigger ones often finish overnight and get handed out the following week.": (
        "Kleine projecten kunnen tijdens de sessie geprint worden; grotere zijn vaak 's nachts klaar en worden de week erna meegegeven.",
        "Les petits projets peuvent s'imprimer pendant la session ; les plus grands se terminent souvent la nuit et sont remis la semaine suivante."),
    "Do we need any design experience?": ("Is ervaring met ontwerpen nodig?", "Faut-il de l'expérience en conception ?"),
    "No — the browser-based tool used here is built for complete beginners, with simple drag-and-resize shapes.": (
        "Nee, het programma in de browser is gemaakt voor echte beginners, met eenvoudige vormen die je versleept en vergroot.",
        "Non : l'outil utilisé dans le navigateur est conçu pour les débutants complets, avec des formes simples à déplacer et redimensionner."),
    "Can we keep what we print?": ("Mogen we houden wat we printen?", "Peut-on garder ce qu'on imprime ?"),
    "Yes — printed projects go home with the ninja who designed them.": (
        "Ja, geprinte projecten gaan mee naar huis met de ninja die ze ontwierp.",
        "Oui : les projets imprimés repartent avec le ninja qui les a conçus."),

    # --- skills --------------------------------------------------------------------
    "3D modelling basics": ("Basis 3D-modelleren", "Bases de la modélisation 3D"),
    "Block coding": ("Programmeren met blokjes", "Programmation par blocs"),
    "CSS styling": ("Opmaak met CSS", "Mise en forme CSS"),
    "Circuits & breadboards": ("Schakelingen en breadboards", "Circuits et plaques d'essai"),
    "Conditionals": ("Voorwaarden", "Conditions"),
    "Data types": ("Gegevenstypes", "Types de données"),
    "Debugging": ("Fouten zoeken", "Débogage"),
    "Debugging hardware": ("Fouten zoeken in hardware", "Débogage matériel"),
    "Events & broadcasting": ("Gebeurtenissen en berichten", "Événements et messages"),
    "Functions": ("Functies", "Fonctions"),
    "GPIO basics": ("Basis GPIO", "Bases du GPIO"),
    "HTML structure": ("HTML-structuur", "Structure HTML"),
    "Inputs & outputs": ("Invoer en uitvoer", "Entrées et sorties"),
    "Iterative design": ("Stap voor stap verbeteren", "Conception itérative"),
    "JavaScript basics": ("Basis JavaScript", "Bases de JavaScript"),
    "Layout & responsive design": ("Lay-out en responsive design", "Mise en page et design adaptatif"),
    "Lists": ("Lijsten", "Listes"),
    "Loops": ("Lussen", "Boucles"),
    "Measurements & scale": ("Afmetingen en schaal", "Mesures et échelle"),
    "Python for hardware": ("Python voor hardware", "Python pour le matériel"),
    "Radio messaging between devices": ("Radioberichten tussen toestellen", "Messages radio entre appareils"),
    "Reading sensors": ("Sensoren uitlezen", "Lire des capteurs"),
    "Sequencing": ("Volgorde", "Séquences"),
    "Slicing & printing basics": ("Basis slicen en printen", "Bases du tranchage et de l'impression"),
    "Variables": ("Variabelen", "Variables"),

    # --- global, dojo and session FAQs ---------------------------------------------------
    "Is it really free?": ("Is het echt gratis?", "C'est vraiment gratuit ?"),
    "Yes — every Dojo session is free, run entirely by volunteers.": (
        "Ja, elke dojosessie is gratis en wordt volledig door vrijwilligers begeleid.",
        "Oui : chaque session de dojo est gratuite et entièrement animée par des bénévoles."),
    "Does my child need coding experience?": ("Moet mijn kind al kunnen programmeren?", "Mon enfant doit-il savoir programmer ?"),
    "No experience needed — we group by age and skill on the day, not in advance.": (
        "Ervaring is niet nodig: we maken groepjes op leeftijd en niveau op de dag zelf, niet op voorhand.",
        "Aucune expérience requise : nous formons les groupes par âge et niveau le jour même, pas à l'avance."),
    "Do parents need to stay?": ("Moeten ouders blijven?", "Les parents doivent-ils rester ?"),
    "Under-12s need an adult on site; older kids can be dropped off.": (
        "Voor kinderen jonger dan 12 moet er een volwassene aanwezig zijn; oudere kinderen mag je afzetten.",
        "Les moins de 12 ans doivent être accompagnés d'un adulte sur place ; les plus grands peuvent être déposés."),
    "Is there parking nearby?": ("Is er parking in de buurt?", "Y a-t-il un parking à proximité ?"),
    "Yes, free parking is available right outside the venue.": (
        "Ja, er is gratis parking vlak voor de deur.", "Oui, un parking gratuit se trouve juste devant le lieu."),
    "Is the venue wheelchair accessible?": ("Is de locatie toegankelijk met een rolstoel?", "Le lieu est-il accessible en fauteuil roulant ?"),
    "Yes, there's step-free access and an accessible toilet.": (
        "Ja, er is een drempelvrije toegang en een aangepast toilet.", "Oui, l'accès est de plain-pied et il y a des toilettes adaptées."),
    "Is there a waitlist if it's full?": ("Is er een wachtlijst als het volzet is?", "Y a-t-il une liste d'attente si c'est complet ?"),
    "Yes — sign up anyway and we'll email you if a spot opens up.": (
        "Ja, schrijf je toch in en we mailen je als er een plaats vrijkomt.",
        "Oui : inscrivez-vous quand même et nous vous écrirons si une place se libère."),
    "Can I drop in late?": ("Mag ik later binnenlopen?", "Puis-je arriver en retard ?"),
    "Yes, just check in at the door — you won't miss much.": (
        "Ja, meld je gewoon aan de deur. Je mist niet veel.", "Oui, présentez-vous simplement à l'entrée : vous ne manquerez pas grand-chose."),

    # --- testimonials (site-wide) --------------------------------------------------------
    "My daughter built her first game in one Saturday morning and hasn't stopped talking about it since.": (
        "Mijn dochter bouwde op één zaterdagvoormiddag haar eerste spel en praat sindsdien over niets anders.",
        "Ma fille a créé son premier jeu en un samedi matin et n'arrête pas d'en parler depuis."),
    "I never thought I'd say this, but my son asks to wake up early on dojo Saturdays.": (
        "Ik had nooit gedacht dat ik dit zou zeggen, maar mijn zoon vraagt om vroeg gewekt te worden op dojozaterdagen.",
        "Je n'aurais jamais cru dire ça, mais mon fils demande à être réveillé tôt les samedis de dojo."),
    "I made a website with my own name on it. My friends at school didn't believe me until I showed them.": (
        "Ik maakte een website met mijn eigen naam erop. Mijn vrienden op school geloofden me pas toen ik hem toonde.",
        "J'ai fait un site avec mon nom dessus. Mes amis à l'école ne m'ont pas cru avant que je le leur montre."),
    "Watching a room of eight-year-olds debug their own Scratch project, patiently, without giving up — that's why I keep coming back to mentor.": (
        "Een zaal vol achtjarigen die geduldig hun eigen Scratch-project debuggen zonder op te geven: daarom blijf ik terugkomen als mentor.",
        "Voir une salle d'enfants de huit ans déboguer patiemment leur propre projet Scratch sans abandonner : c'est pour ça que je reviens être mentor."),
    "It's free, it's local, and the mentors clearly love doing this. What more could you ask for on a Saturday morning?": (
        "Het is gratis, het is dichtbij en de mentors doen het duidelijk graag. Wat wil je nog meer op een zaterdagvoormiddag?",
        "C'est gratuit, c'est près de chez nous et les mentors adorent visiblement ce qu'ils font. Que demander de plus un samedi matin ?"),
    "We flashed our first program onto a micro:bit and my daughter wore it around her neck for a week.": (
        "We zetten ons eerste programma op een micro:bit en mijn dochter droeg hem een week lang rond haar nek.",
        "Nous avons chargé notre premier programme sur un micro:bit et ma fille l'a porté autour du cou pendant une semaine."),
    "I started as a ninja here at 10. I'm 17 now and mentoring the next group — this place is why I'm studying computer science.": (
        "Ik begon hier als ninja op mijn tiende. Nu ben ik 17 en mentor voor de volgende groep. Door deze plek studeer ik informatica.",
        "J'ai commencé ici comme ninja à 10 ans. J'en ai 17 et j'encadre le groupe suivant : c'est grâce à cet endroit que j'étudie l'informatique."),
    "parent": ("ouder", "parent"),
    "ninja": ("ninja", "ninja"),
    "volunteer mentor": ("vrijwillige mentor", "mentor bénévole"),
    "ninja mentor": ("ninja-mentor", "ninja mentor"),

    # --- organisation team listing ----------------------------------------------------------
    "Chair, software engineer": ("Voorzitter, software-engineer", "Présidente, ingénieure logiciel"),
    "Priya co-founded the Belgian chapter network and now chairs the board, focusing on keeping every dojo funded and stocked with mentors.": (
        "Priya richtte mee het Belgische netwerk van dojo's op en is nu voorzitter van het bestuur. Ze zorgt ervoor dat elke dojo middelen en mentors heeft.",
        "Priya a cofondé le réseau belge des dojos et préside aujourd'hui le conseil ; elle veille à ce que chaque dojo ait des moyens et des mentors."),
    "Chapter growth, Partnerships": ("Groei van het netwerk, Partnerschappen", "Croissance du réseau, Partenariats"),
    "Treasurer, accountant": ("Penningmeester, boekhouder", "Trésorier, comptable"),
    "Tom keeps the books straight across every dojo's small grants and sponsor contributions, and helps new chapters get set up financially.": (
        "Tom houdt de boekhouding bij van de kleine subsidies en sponsorbijdragen van elke dojo, en helpt nieuwe dojo's financieel op weg.",
        "Tom tient les comptes des petites subventions et contributions des sponsors de chaque dojo, et aide les nouveaux dojos à s'organiser financièrement."),
    "Finance, Grants": ("Financiën, Subsidies", "Finances, Subventions"),
    "Volunteer coordinator": ("Coördinator vrijwilligers", "Coordinatrice des bénévoles"),
    "Nathalie matches new mentor sign-ups to dojos that need them, and runs the onboarding session every mentor goes through before their first Saturday.": (
        "Nathalie koppelt nieuwe mentors aan dojo's die hen nodig hebben, en geeft de onthaalsessie die elke mentor volgt voor de eerste zaterdag.",
        "Nathalie oriente les nouveaux mentors vers les dojos qui en ont besoin et anime la session d'accueil que chaque mentor suit avant son premier samedi."),
    "Volunteer recruitment, Onboarding": ("Vrijwilligers werven, Onthaal", "Recrutement de bénévoles, Accueil"),
    "Partnerships lead": ("Verantwoordelijke partnerschappen", "Responsable des partenariats"),
    "Bram builds relationships with local libraries, schools and companies willing to host a dojo or sponsor equipment.": (
        "Bram bouwt relaties op met bibliotheken, scholen en bedrijven die een dojo willen ontvangen of materiaal willen sponsoren.",
        "Bram noue des liens avec les bibliothèques, écoles et entreprises prêtes à accueillir un dojo ou à sponsoriser du matériel."),
    "Partnerships, Events": ("Partnerschappen, Evenementen", "Partenariats, Événements"),

    # --- belts and badges -----------------------------------------------------------------------
    "White belt": ("Witte gordel", "Ceinture blanche"),
    "Opens a coding tool and follows a guided project.": ("Opent een programmeertool en volgt een begeleid project.", "Ouvre un outil de programmation et suit un projet guidé."),
    "Yellow belt": ("Gele gordel", "Ceinture jaune"),
    "Finishes a beginner project on their own.": ("Werkt zelf een beginnersproject af.", "Termine seul un projet pour débutants."),
    "Orange belt": ("Oranje gordel", "Ceinture orange"),
    "Changes a project to make it their own: new sprites, rules or levels.": (
        "Past een project aan tot het van hem of haar is: nieuwe figuren, regels of levels.",
        "Modifie un projet pour se l'approprier : nouveaux personnages, règles ou niveaux."),
    "Green belt": ("Groene gordel", "Ceinture verte"),
    "Uses variables, loops and conditions without help.": ("Gebruikt zonder hulp variabelen, lussen en voorwaarden.", "Utilise sans aide des variables, des boucles et des conditions."),
    "Blue belt": ("Blauwe gordel", "Ceinture bleue"),
    "Plans and builds a small project of their own from scratch.": ("Plant en bouwt van nul een eigen klein project.", "Planifie et construit de zéro un petit projet personnel."),
    "Purple belt": ("Paarse gordel", "Ceinture violette"),
    "Finds and fixes bugs in their own and other ninjas' code.": ("Vindt en herstelt fouten in eigen code en die van andere ninja's.", "Trouve et corrige les bugs dans son code et celui des autres ninjas."),
    "Brown belt": ("Bruine gordel", "Ceinture marron"),
    "Builds a complete project in a text-based language (Python, JavaScript, ...).": (
        "Bouwt een volledig project in een programmeertaal met tekst (Python, JavaScript, ...).",
        "Construit un projet complet dans un langage textuel (Python, JavaScript, ...)."),
    "Red belt": ("Rode gordel", "Ceinture rouge"),
    "Helps other ninjas and explains how their code works.": ("Helpt andere ninja's en legt uit hoe hun code werkt.", "Aide les autres ninjas et explique comment leur code fonctionne."),
    "Black belt": ("Zwarte gordel", "Ceinture noire"),
    "Builds and presents an ambitious project, e.g. at Coolest Projects.": (
        "Bouwt en presenteert een ambitieus project, bv. op Coolest Projects.",
        "Construit et présente un projet ambitieux, p. ex. à Coolest Projects."),
    "White Band": ("Wit bandje", "Bracelet blanc"),
    "Came to their first CoderDojo session.": ("Kwam naar een eerste CoderDojo-sessie.", "Est venu à sa première session CoderDojo."),
    "Green Band": ("Groen bandje", "Bracelet vert"),
    "Back for the fifth time — a regular in the making.": ("Voor de vijfde keer terug: een vaste bezoeker in wording.", "De retour pour la cinquième fois : un habitué en devenir."),
    "Red Band": ("Rood bandje", "Bracelet rouge"),
    "Ten sessions in — a genuine dojo regular.": ("Tien sessies: een echte vaste bezoeker.", "Dix sessions : un véritable habitué du dojo."),
    "Black Band": ("Zwart bandje", "Bracelet noir"),
    "Fifteen sessions. A CoderDojo veteran.": ("Vijftien sessies. Een echte CoderDojo-veteraan.", "Quinze sessions. Un vétéran de CoderDojo."),
    "Code Explorer": ("Code-ontdekker", "Explorateur du code"),
    "Tried a pathway all the way through to a finished project.": ("Volgde een leertraject tot en met een afgewerkt project.", "A suivi un parcours jusqu'à un projet terminé."),
    "Complete a pathway project.": ("Werk een project van een leertraject af.", "Terminer un projet d'un parcours."),
    "Game Maker": ("Spelletjesmaker", "Créateur de jeux"),
    "Built a working game from scratch (pun intended).": ("Bouwde van nul een werkend spel (in Scratch of niet).", "A créé un jeu qui fonctionne en partant de zéro."),
    "Build and share a playable game.": ("Bouw en deel een speelbaar spel.", "Créer et partager un jeu jouable."),
    "CoderDojo for Girls": ("CoderDojo voor meisjes", "CoderDojo pour les filles"),
    "Came along to a CoderDojo for Girls session.": ("Kwam naar een CoderDojo-sessie voor meisjes.", "Est venue à une session CoderDojo pour les filles."),
    "Attend a CoderDojo for Girls session.": ("Kom naar een CoderDojo-sessie voor meisjes.", "Participer à une session CoderDojo pour les filles."),
    "Coolest Projects 2026": ("Coolest Projects 2026", "Coolest Projects 2026"),
    "Showed off a project at Coolest Projects 2026.": ("Toonde een project op Coolest Projects 2026.", "A présenté un projet à Coolest Projects 2026."),
    "Attend Coolest Projects 2026.": ("Kom naar Coolest Projects 2026.", "Participer à Coolest Projects 2026."),

    # --- dojo texts (seed_mentors) ------------------------------------------------------------------
    "Seeing a kid's face light up when their code finally runs — that's the whole job.": (
        "Het gezicht van een kind zien oplichten als de code eindelijk werkt: daar doen we het voor.",
        "Voir le visage d'un enfant s'illuminer quand son code fonctionne enfin : c'est tout le sens de notre travail."),
    ("### What makes us different\n\n"
     "We've been running since our very first Saturday in the local library, and it's still "
     "mentors and ninjas building things together — no lectures, no pressure.\n\n"
     "**Everyone is welcome:** siblings, first-timers, and kids who've been coming for years "
     "all work side by side."): (
        "### Wat ons anders maakt\n\n"
        "We zijn begonnen op een eerste zaterdag in de bibliotheek, en nog altijd bouwen mentors en ninja's "
        "samen dingen: geen lessen, geen druk.\n\n"
        "**Iedereen is welkom:** broers en zussen, nieuwkomers en kinderen die al jaren komen, werken zij aan zij.",
        "### Ce qui nous distingue\n\n"
        "Nous avons commencé un premier samedi à la bibliothèque, et ce sont toujours les mentors et les ninjas "
        "qui construisent ensemble : pas de cours magistral, pas de pression.\n\n"
        "**Tout le monde est bienvenu :** frères et sœurs, nouveaux venus et enfants présents depuis des années "
        "travaillent côte à côte."),
    ("### Parking\n\n"
     "Free parking is available right outside — look for the visitor spots near the main entrance.\n\n"
     "### Getting in\n\n"
     "Enter through the side door and follow the signs; someone will be there to greet you from 15 minutes before the start."): (
        "### Parking\n\n"
        "Er is gratis parking vlak voor de deur: zoek de bezoekersplaatsen bij de hoofdingang.\n\n"
        "### Binnenkomen\n\n"
        "Kom binnen langs de zijdeur en volg de bordjes; vanaf 15 minuten voor de start staat er iemand om je te ontvangen.",
        "### Parking\n\n"
        "Un parking gratuit se trouve juste devant : cherchez les places visiteurs près de l'entrée principale.\n\n"
        "### Entrée\n\n"
        "Entrez par la porte latérale et suivez les panneaux ; quelqu'un vous accueille dès 15 minutes avant le début."),

    # --- announcements (seed_announcements; "{dojo}" is the dojo's name) -------------------------------
    "We've moved to a bigger room from next month — same time, same entrance, just more elbow room.": (
        "Vanaf volgende maand zitten we in een grotere zaal: zelfde uur, zelfde ingang, gewoon meer plaats.",
        "Dès le mois prochain, nous passons dans une plus grande salle : même heure, même entrée, juste plus de place."),
    "Looking for one more volunteer mentor comfortable with Python for alternate sessions. Get in touch if that's you!": (
        "We zoeken nog een vrijwillige mentor die Python kent, voor om de twee sessies. Laat iets weten als jij dat bent!",
        "Nous cherchons encore un mentor bénévole à l'aise en Python pour une session sur deux. Contactez-nous si c'est vous !"),
    "Thanks to a local sponsor we now have six loaner laptops. No laptop at home? Just let us know when you sign up.": (
        "Dankzij een lokale sponsor hebben we nu zes laptops om uit te lenen. Geen laptop thuis? Laat het weten bij je inschrijving.",
        "Grâce à un sponsor local, nous avons maintenant six ordinateurs à prêter. Pas d'ordinateur à la maison ? Dites-le-nous à l'inscription."),
    "Our micro:bits have arrived! Ninjas who want to try physical computing can ask a mentor on the day.": (
        "Onze micro:bits zijn er! Ninja's die met elektronica willen beginnen, kunnen het op de dag zelf aan een mentor vragen.",
        "Nos micro:bits sont arrivés ! Les ninjas qui veulent essayer l'électronique peuvent le demander à un mentor le jour même."),
    "Three of our ninjas are presenting their projects at Coolest Projects this year. Come and cheer them on!": (
        "Drie van onze ninja's stellen dit jaar hun project voor op Coolest Projects. Kom hen aanmoedigen!",
        "Trois de nos ninjas présentent leur projet à Coolest Projects cette année. Venez les encourager !"),
    "Reminder: please bring a charger for your laptop, the room has plenty of sockets.": (
        "Herinnering: breng een lader mee voor je laptop, er zijn genoeg stopcontacten in de zaal.",
        "Rappel : pensez au chargeur de votre ordinateur, la salle a assez de prises."),
    "The entrance on the side of the building is closed for works; use the main door this month.": (
        "De zij-ingang is gesloten door werken; gebruik deze maand de hoofdingang.",
        "L'entrée latérale est fermée pour travaux ; utilisez la porte principale ce mois-ci."),
    "{dojo} is taking a short summer break. Sessions start again in September.": (
        "{dojo} neemt een korte zomerpauze. De sessies beginnen opnieuw in september.",
        "{dojo} fait une courte pause estivale. Les sessions reprennent en septembre."),
    "New this term: a beginners' corner for first-timers, with a mentor dedicated to getting you started.": (
        "Nieuw dit trimester: een beginnershoek voor nieuwkomers, met een mentor die je helpt starten.",
        "Nouveau ce trimestre : un coin débutants pour les nouveaux, avec un mentor pour vous lancer."),
    "Parents are welcome to stay and watch, there's coffee in the hall.": (
        "Ouders mogen blijven kijken, er is koffie in de gang.",
        "Les parents peuvent rester regarder, il y a du café dans le hall."),
    "We're trying out a web development track. Ninjas who finished a Scratch project can give it a go.": (
        "We proberen een reeks rond webontwikkeling uit. Ninja's die een Scratch-project afwerkten, kunnen meedoen.",
        "Nous testons un parcours développement web. Les ninjas qui ont terminé un projet Scratch peuvent l'essayer."),
    "Big thank you to everyone who came to our open day. Over twenty new ninjas signed up!": (
        "Een dikke merci aan iedereen die naar onze opendeurdag kwam. Meer dan twintig nieuwe ninja's schreven zich in!",
        "Un grand merci à tous ceux qui sont venus à notre journée portes ouvertes. Plus de vingt nouveaux ninjas se sont inscrits !"),
    "Our Raspberry Pi kits are back from repair, so the hardware table is open again.": (
        "Onze Raspberry Pi-kits zijn terug van herstelling, dus de elektronicatafel is weer open.",
        "Nos kits Raspberry Pi sont revenus de réparation : la table électronique est de nouveau ouverte."),
    "Mentors: team meeting after next session to plan the rest of the season.": (
        "Mentors: teamoverleg na de volgende sessie om de rest van het seizoen te plannen.",
        "Mentors : réunion d'équipe après la prochaine session pour planifier la suite de la saison."),

    # --- session names (events.template_images) and the organisation's events ------------------------
    "Coding Saturday": ("Codeerzaterdag", "Samedi code"),
    "Open Lab": ("Open lab", "Labo ouvert"),
    "Scratch & Games": ("Scratch en spelletjes", "Scratch et jeux"),
    "Build & Code": ("Bouwen en coderen", "Construire et coder"),
    "Ninja Session": ("Ninjasessie", "Session ninja"),
    "Code Club": ("Codeerclub", "Club de code"),
    "Make Something Session": ("Maak-iets-sessie", "Session création"),
    "Project Time": ("Projecttijd", "Temps projet"),
    "Beginner's Workshop": ("Workshop voor beginners", "Atelier débutants"),
    "Game Jam Session": ("Game jam", "Game jam"),
    "CoderDojo Girlz: Build your first website": ("CoderDojo Girlz: bouw je eerste website", "CoderDojo Girlz : créez votre premier site web"),
    "An afternoon for girls who want to try coding: build and publish your own web page, with mentors on hand the whole time. No experience needed.": (
        "Een namiddag voor meisjes die willen leren programmeren: bouw en publiceer je eigen webpagina, met mentors die de hele tijd klaarstaan. Geen ervaring nodig.",
        "Un après-midi pour les filles qui veulent essayer le code : créez et publiez votre propre page web, avec des mentors présents tout du long. Aucune expérience requise."),
    "Coolest Projects Belgium": ("Coolest Projects België", "Coolest Projects Belgique"),
    "The yearly showcase where young makers show what they built: games, websites, robots, apps and more. Registration and project submission happen on the Coolest Projects website.": (
        "De jaarlijkse tentoonstelling waar jonge makers tonen wat ze bouwden: spelletjes, websites, robots, apps en meer. Inschrijven en projecten indienen gebeurt op de website van Coolest Projects.",
        "La vitrine annuelle où les jeunes créateurs montrent ce qu'ils ont construit : jeux, sites web, robots, applis et plus. L'inscription et le dépôt des projets se font sur le site de Coolest Projects."),
    "A CoderDojo for Girls session, run for the International Day of Women and Girls in Science.": (
        "Een CoderDojo-sessie voor meisjes, georganiseerd voor de Internationale Dag van Vrouwen en Meisjes in de Wetenschap.",
        "Une session CoderDojo pour les filles, organisée pour la Journée internationale des femmes et des filles de science."),
    "CoderDojo's yearly showcase — ninjas demo the projects they've been building all year.": (
        "De jaarlijkse tentoonstelling van CoderDojo: ninja's tonen de projecten waaraan ze het hele jaar bouwden.",
        "La vitrine annuelle de CoderDojo : les ninjas présentent les projets qu'ils ont construits toute l'année."),
    "The organisation behind CoderDojo in Belgium.": ("De organisatie achter CoderDojo in België.", "L'organisation derrière CoderDojo en Belgique."),
    "Show the world what you made. Sign up your project now!": (
        "Toon de wereld wat je maakte. Schrijf je project nu in!", "Montrez au monde ce que vous avez créé. Inscrivez votre projet maintenant !"),
    "Not near a dojo? Join our girls' afternoon in Ghent.": (
        "Geen dojo in de buurt? Kom naar onze meisjesnamiddag in Gent.", "Pas de dojo près de chez vous ? Rejoignez notre après-midi pour filles à Gand."),
}

GIRLZ_PREFIX = {EN: "CoderDojo Girlz: ", NL: "CoderDojo Girlz: ", FR: "CoderDojo Girlz : "}

# The seeded session description (events.management.commands.seed_events.description_for).
SESSION_DESCRIPTION = {
    NL: (
        "**{name}** is een sessie voor beginners waarin je zelf aan de slag gaat. Wat je doet:\n\n"
        "- Kies een project en begin te bouwen\n"
        "- Krijg hulp van een mentor als je vastzit\n"
        "- Toon op het einde wat je maakte (helemaal vrijblijvend)\n\n"
        "### Breng mee\n\n"
        "- Een laptop, als je er een hebt (we hebben er een paar om te lenen)\n"
        "- Een drinkfles en een tussendoortje\n\n"
        "### Niet nodig\n\n"
        "Geen ervaring, geen accounts om vooraf aan te maken: we helpen je op de dag zelf op weg."
    ),
    FR: (
        "**{name}** est une session pratique, idéale pour débuter. Au programme :\n\n"
        "- Choisir un projet et commencer à construire\n"
        "- Recevoir l'aide d'un mentor dès que vous bloquez\n"
        "- Montrer ce que vous avez créé à la fin (tout à fait facultatif)\n\n"
        "### À apporter\n\n"
        "- Un ordinateur portable, si vous en avez un (nous en avons quelques-uns à prêter)\n"
        "- Une gourde et une collation\n\n"
        "### Pas nécessaire\n\n"
        "Aucune expérience, aucun compte à créer à l'avance : nous vous aidons à démarrer sur place."
    ),
}


def translate(text, language, dojo_name=""):
    """`text` (an English seed text) in `language`, or None when it isn't one."""
    if language == EN:
        return text
    index = {NL: 0, FR: 1}[language]
    if text in T:
        return T[text][index]
    if dojo_name:
        for english, versions in T.items():
            if "{dojo}" in english and english.format(dojo=dojo_name) == text:
                return versions[index].format(dojo=dojo_name)
    if text.startswith(GIRLZ_PREFIX[EN]):
        rest = translate(text[len(GIRLZ_PREFIX[EN]):], language)
        return GIRLZ_PREFIX[language] + rest if rest else None
    return None


def translate_session_description(text, english_name, language):
    """The seeded session description in `language`, when `text` is the
    English one seed_events wrote for `english_name`."""
    from events.management.commands.seed_events import description_for

    if text != description_for(english_name):
        return None
    if language == EN:
        return text
    return SESSION_DESCRIPTION[language].format(name=translate(english_name, language) or english_name)
