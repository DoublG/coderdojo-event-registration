from django.core.management.base import BaseCommand

from content.models import FAQ
from core.image_library import use_library_image
from pathways.models import Pathway, PathwayProject, PathwayStep, Skill

# Modelled on the real learning paths CoderDojo chapters run today via the
# Raspberry Pi Foundation's own project library (projects.raspberrypi.org) —
# Scratch, Python and web development are Foundation/Intermediate pathways
# there; micro:bit, Raspberry Pi GPIO ("physical computing") and 3D design
# are the common "make something real" tracks most dojos add once a ninja
# is past the basics.
PATHWAYS = [
    {
        "name": "Scratch",
        "image": "scratch.svg",
        "subtitle": "Drag-and-drop blocks and real games from your very first Saturday — no experience needed.",
        "description": (
            "Scratch is where almost every ninja starts. Instead of typing code, you snap together "
            "coloured blocks to make a character move, react and keep score — so you're building a real "
            "game or animation in your first session, mistakes and all. It's the same block-based approach "
            "used in schools everywhere, just with a mentor next to you and a room full of other kids "
            "building their own thing at the same time."
        ),
        "min_age": 7,
        "max_age": 10,
        "no_experience_needed": True,
        "runs_in_browser": True,
        "skills": ["Sequencing", "Loops", "Conditionals", "Events & broadcasting", "Variables", "Debugging"],
        "steps": [
            ("Pick a starter project", "Mentors bring a few ready-to-remix projects along for anyone who wants a running start."),
            ("Make it your own", "Change the art, the rules, the story — it's not finished until you've broken something on purpose."),
            ("Show the group", "Most sessions end with a few kids sharing their screen — no pressure, just show-and-tell."),
        ],
        "projects": [
            ("A platformer game", "Design your own levels, add a jumping hero, and make it a little harder to beat with each try."),
            ("A quiz game", "Write your own questions and keep score when a friend picks up the controls."),
            ("An animated card", "Combine sprites, sound and a bit of logic into something you can actually send someone."),
        ],
        "faqs": [
            ("How long does the Scratch pathway take?", "There's no fixed length — most kids spend a few sessions here before trying Python or Web, and some stay much longer. It's fine either way."),
            ("My child already knows Scratch — should they still start here?", "Not necessarily — a mentor can place them straight into Python or Web on their very first visit."),
            ("Do they need to install anything at home?", "No — Scratch runs in the browser on the dojo's own laptops, so there's nothing to install beforehand."),
        ],
    },
    {
        "name": "Python",
        "image": "python.svg",
        "subtitle": "Trade the blocks for real code and build your first text-based games and programs.",
        "description": (
            "Python is usually the next step after Scratch, though plenty of kids start here directly. "
            "You're writing actual lines of code in a real, widely-used programming language — the same one "
            "used for data science, web backends and much more — but the projects stay small and fun: a "
            "bot that quizzes your friends, a game of hangman, a program that always wins at rock-paper-scissors "
            "(or always loses, if that's funnier)."
        ),
        "min_age": 10,
        "max_age": 14,
        "no_experience_needed": True,
        "runs_in_browser": True,
        "skills": ["Variables", "Data types", "Loops", "Conditionals", "Functions", "Lists", "Debugging"],
        "steps": [
            ("Start from a template", "A short starter script gets everyone past the blank-page problem in the first five minutes."),
            ("Add your own twist", "New questions, new rules, new random events — small changes that make the program feel like yours."),
            ("Trade with a friend", "Swap programs with someone else and try to break each other's — it's the fastest way to find real bugs."),
        ],
        "projects": [
            ("A quiz bot", "Write your own questions, keep score, and tell the player how they did at the end."),
            ("Hangman", "Guess the letters, track the wrong guesses, and pick your own word list."),
            ("Rock-paper-scissors", "Play against the computer, keep a running score, and add a few trick moves if you're feeling bold."),
        ],
        "faqs": [
            ("Does my child need to know Scratch first?", "It helps but isn't required — some kids find typed code easier to reason about than blocks."),
            ("What do they code in?", "A browser-based Python editor, so there's nothing to install and mentors can see everyone's screen easily."),
            ("What if they get a syntax error and get stuck?", "That's most of the session, for everyone — mentors treat error messages as the normal next step, not a wrong turn."),
        ],
    },
    {
        "name": "Web Development",
        "image": "web.svg",
        "subtitle": "Design and publish your own website with HTML, CSS and a bit of JavaScript.",
        "description": (
            "Every website you've ever visited is built from the same three building blocks: HTML for the "
            "content, CSS for how it looks, and JavaScript for what it does when you click something. This "
            "pathway builds all three up gradually — you'll have a page with your own words and images on "
            "it in the first session, then spend later ones making it look good and adding little interactive "
            "touches."
        ),
        "min_age": 10,
        "max_age": 18,
        "no_experience_needed": True,
        "runs_in_browser": True,
        "skills": ["HTML structure", "CSS styling", "Layout & responsive design", "JavaScript basics", "Debugging"],
        "steps": [
            ("Write the content first", "Headings, paragraphs and images go in before any styling — a webpage in plain HTML still works, it's just plain."),
            ("Style it with CSS", "Colours, fonts and spacing turn the plain page into something that looks like a real site."),
            ("Add one interactive touch", "A button that changes something, a simple quiz, a photo that swaps on click — small JavaScript, big satisfaction."),
        ],
        "projects": [
            ("A personal profile page", "Introduce yourself, your hobbies and your favourite things with your own layout and colours."),
            ("A photo gallery", "Lay out a grid of images with captions, and make it look good on both a laptop and a phone."),
            ("An interactive quiz page", "Ask a question, check the answer with a bit of JavaScript, and reveal a result."),
        ],
        "faqs": [
            ("Do they need to know how to type well?", "Not especially — most of a session is spent thinking through the page's structure, and mentors help with the typing-heavy bits."),
            ("Will their website be online for real?", "Not by default — pages are built and viewed locally during the session, though a mentor can point interested families toward free hosting afterwards."),
            ("Is this the same as app development?", "No — this pathway is about websites specifically. Ninjas curious about apps are usually pointed toward Python or Unity instead."),
        ],
    },
    {
        "name": "BBC micro:bit",
        "image": "microbit.svg",
        "subtitle": "Code a tiny physical computer — lights, buttons and sensors you can hold in your hand.",
        "description": (
            "The micro:bit is a small, real computer with its own lights, buttons, compass and radio — and "
            "you program it with the same drag-and-drop blocks as Scratch (or Python, if you'd rather type). "
            "The difference is what happens next: you plug it in, and the code runs on an actual device you "
            "can hold, shake, wear or race against a friend's."
        ),
        "min_age": 8,
        "max_age": 14,
        "no_experience_needed": True,
        "runs_in_browser": True,
        "skills": ["Block coding", "Inputs & outputs", "Loops", "Variables", "Radio messaging between devices"],
        "steps": [
            ("Design on screen first", "Every project starts in the browser-based editor, so you can test the logic before it touches a real device."),
            ("Flash it to a micro:bit", "One click sends your code onto the board — plugged in over USB, no extra setup needed."),
            ("Test it for real", "Shake it, press its buttons, walk around with it — physical testing finds things the simulator can't."),
        ],
        "projects": [
            ("A reaction-time game", "Light up randomly and see how fast a friend can press the button."),
            ("A step counter", "Use the built-in accelerometer to count steps and show the total on the LED display."),
            ("Tilt rock-paper-scissors", "Shake to pick a move and use radio to play against a friend's micro:bit."),
        ],
        "faqs": [
            ("Do we need to bring our own micro:bit?", "No — most dojos keep a set of boards and USB cables on hand to borrow for the session."),
            ("Is this just Scratch on a different screen?", "It starts similarly (drag-and-drop blocks) but the moment your code controls a physical light or button, it feels very different."),
            ("Can my child take their project home?", "The code, yes — projects save to the browser and export as a file. The physical micro:bit itself usually stays with the dojo's kit."),
        ],
    },
    {
        "name": "Raspberry Pi (physical computing)",
        "image": "raspberrypi.svg",
        "subtitle": "Wire up real circuits and control them with code — lights, sensors, buzzers and more.",
        "description": (
            "This is where code meets a breadboard. Using a Raspberry Pi's GPIO pins, you'll wire up real "
            "components — LEDs, buttons, buzzers, sensors — and write Python to control them. It's slower and "
            "more hands-on than screen-only pathways (there's wiring to get right, not just code), which is "
            "exactly what makes it satisfying: a program that makes a physical light blink on command.\n\n"
            "The same pathway also covers microcontrollers: an Arduino runs one program the moment it gets "
            "power, which makes it ideal for robots, lights and sensors, and an ESP32 adds Wi-Fi and "
            "Bluetooth, so a project can send its measurements to a phone or a web page."
        ),
        "min_age": 10,
        "max_age": 18,
        "no_experience_needed": False,
        "runs_in_browser": False,
        "skills": ["GPIO basics", "Circuits & breadboards", "Python for hardware", "Reading sensors", "Debugging hardware",
                   "Arduino programming", "Wi-Fi projects with ESP32"],
        "steps": [
            ("Wire the circuit", "Follow a diagram to connect components to the right GPIO pins — a mentor checks the wiring before anything gets powered on."),
            ("Write the code", "Python controls the circuit: turning pins on and off, or reading a sensor's value."),
            ("Test, then debug the wiring or the code", "If it doesn't work, it's usually one or the other — working out which is most of the skill here."),
        ],
        "projects": [
            ("A traffic light sequence", "Wire three LEDs and time a proper red-amber-green-amber sequence in code."),
            ("A burglar alarm", "A motion sensor triggers a buzzer and a flashing light — with a keypad code to disarm it."),
            ("A mini weather station", "Read temperature and humidity from a sensor and log or display the results."),
            ("A plant-watering alarm with Arduino", "A soil-moisture sensor on an Arduino beeps and lights up when the plant needs water."),
            ("A Wi-Fi thermometer with an ESP32", "The ESP32 serves a small web page that shows the room's temperature on any phone on the same network."),
        ],
        "faqs": [
            ("Is prior coding experience required?", "Basic Python (variables, loops, functions) helps a lot — mentors usually suggest finishing a few Python sessions first."),
            ("What if we let out the magic smoke?", "It happens — mentors check wiring before power-on specifically to keep this rare, and the dojo keeps spare components on hand."),
            ("Do we need our own Raspberry Pi?", "No — the dojo's kit includes boards, breadboards, jumper wires and a starter set of components to borrow for the session."),
            ("Raspberry Pi, Arduino or ESP32: what's the difference?", "A Raspberry Pi is a small computer with its own operating system; an Arduino is a microcontroller that runs one program as soon as it's powered; an ESP32 is a microcontroller with Wi-Fi and Bluetooth. Mentors help pick the right board for the project."),
        ],
    },
    {
        "name": "3D Printing",
        "image": "3dprinting.svg",
        "subtitle": "Design something in 3D on screen, then watch it actually get printed.",
        "description": (
            "You design a real, physical object — a keyring, a phone stand, a custom cookie cutter — using "
            "simple browser-based 3D modelling, then send it to a 3D printer and watch it get built up layer "
            "by layer. It's less about coding and more about spatial thinking and iteration: your first version "
            "rarely fits or works quite right, and fixing that is the whole point."
        ),
        "min_age": 8,
        "max_age": 18,
        "no_experience_needed": True,
        "runs_in_browser": True,
        "skills": ["3D modelling basics", "Measurements & scale", "Iterative design", "Slicing & printing basics"],
        "steps": [
            ("Sketch the idea", "A quick pencil sketch with rough measurements saves a lot of on-screen guessing later."),
            ("Model it in the browser", "Simple shapes are combined, stretched and cut to build up the final design."),
            ("Print, check, and refine", "First prints rarely come out perfect — measuring what's wrong and adjusting the model is where most of the learning happens."),
        ],
        "projects": [
            ("A keyring", "A small, quick-printing first project — a name, an initial, or a simple shape."),
            ("A phone stand", "Design angled supports that actually hold a phone up without tipping over."),
            ("A custom cookie cutter", "Trace or design a shape, then think through wall thickness so it holds together and actually cuts."),
        ],
        "faqs": [
            ("How long does a print take?", "Small projects can print during the session; bigger ones often finish overnight and get handed out the following week."),
            ("Do we need any design experience?", "No — the browser-based tool used here is built for complete beginners, with simple drag-and-resize shapes."),
            ("Can we keep what we print?", "Yes — printed projects go home with the ninja who designed them."),
        ],
    },
    {
        "name": "mBot",
        "image": "mbot.svg",
        "subtitle": "Build and program a small robot that drives, follows lines and avoids obstacles.",
        "description": (
            "mBot is a small educational robot on wheels, with sensors for light, distance and lines. You "
            "program it with blocks in mBlock, which works just like Scratch, so a first drive around the "
            "table happens in the first session. After that it's about making the robot smarter: following a "
            "line, stopping before a wall, or racing through an obstacle course built by the other ninjas."
        ),
        "min_age": 8,
        "max_age": 14,
        "no_experience_needed": True,
        "runs_in_browser": True,
        "skills": ["Block coding", "Sensors", "Loops", "Conditionals", "Robotics basics"],
        "steps": [
            ("Meet the robot", "Find the motors, the lights and the sensors, and make the robot drive a square."),
            ("Add a sensor", "Use the distance or line sensor so the robot reacts to what's around it."),
            ("Take on a challenge", "An obstacle course or a line to follow: test, adjust and try again."),
        ],
        "projects": [
            ("A line follower", "Make the robot follow a black line on the floor without losing it in the bends."),
            ("An obstacle avoider", "The ultrasonic sensor spots a wall and the robot turns before it bumps into it."),
            ("A remote-controlled racer", "Steer the robot with the keyboard or the remote and race against another team."),
        ],
        "faqs": [
            ("Do we need our own mBot?", "No — the dojo lends out robots, batteries and cables during the session."),
            ("Is it hard to program?", "No — mBlock uses the same kind of blocks as Scratch; ninjas who want to can switch to Python later."),
            ("From what age can children join?", "From about eight years old, as soon as a child can follow a short Scratch project."),
        ],
    },
    {
        "name": "Sonic Pi",
        "image": "sonicpi.svg",
        "subtitle": "Make music with code: beats, melodies and live-coding.",
        "description": (
            "Sonic Pi turns code into music. A few lines play a beat, a loop keeps it going, and changing a "
            "number while it plays changes the song right away: that's called live-coding, and DJs do it on "
            "stage. Along the way ninjas learn loops, variables and randomness, and they end the session with a "
            "track of their own."
        ),
        "min_age": 10,
        "max_age": 18,
        "no_experience_needed": True,
        "runs_in_browser": False,
        "skills": ["Loops", "Variables", "Randomness", "Timing & rhythm", "Live-coding"],
        "steps": [
            ("Play your first sound", "One line of code plays a note, a second one plays a drum sample."),
            ("Loop a beat", "A live loop keeps the beat going while you add melodies and effects."),
            ("Perform it live", "Change the code while the music plays and show your track to the group."),
        ],
        "projects": [
            ("A drum beat", "Build a beat from samples and play with the tempo until it grooves."),
            ("Your own melody", "Write a tune note by note, then let the code pick random notes from a scale."),
            ("A live-coding set", "Combine loops and effects and change them live, like a DJ."),
        ],
        "faqs": [
            ("Do you need to know music?", "No — ninjas learn about rhythm and notes along the way, and experimenting is the whole point."),
            ("Does it make a lot of noise?", "Everyone works with headphones; bring your own if you have them."),
            ("Can we use Sonic Pi at home?", "Yes — Sonic Pi is free for Windows, macOS, Linux and Raspberry Pi."),
        ],
    },
    {
        "name": "Unity",
        "image": "unity.svg",
        "subtitle": "Build your own 2D and 3D games with a real game engine.",
        "description": (
            "Unity is the game engine behind many well-known games. Ninjas build a world with objects, "
            "physics and a camera, and bring it to life with scripts in C#. It's a big step up from Scratch, "
            "so it suits older ninjas who already know a little coding, but the reward is a game that looks "
            "and plays like a real one."
        ),
        "min_age": 12,
        "max_age": 18,
        "no_experience_needed": False,
        "runs_in_browser": False,
        "skills": ["Game design", "C# basics", "Physics & collisions", "3D scenes", "Debugging"],
        "steps": [
            ("Build the scene", "Place a floor, walls, a player and a camera, and let physics do its work."),
            ("Write a script", "A short C# script makes the player move and jump, and counts the points."),
            ("Test and share", "Play your own game, fix what's off, and let others try it."),
        ],
        "projects": [
            ("A roll-a-ball game", "Roll a ball through a level and collect all the coins against the clock."),
            ("A 2D platformer", "Jump across platforms, avoid enemies and reach the flag."),
            ("A small 3D world", "Build a world with its own obstacles and walk through it in first person."),
        ],
        "faqs": [
            ("What do you need to know first?", "Some experience with Scratch or Python helps a lot: Unity uses C#, a real programming language."),
            ("Does Unity work on every laptop?", "Unity needs a fairly powerful laptop; the dojo checks which laptops are suitable."),
            ("Is Unity free?", "Yes — Unity is free for personal use and learning."),
        ],
    },
]


class Command(BaseCommand):
    help = ("Seed the learning pathways (Scratch, Python, Web, micro:bit, Raspberry Pi with Arduino and ESP32, 3D printing, "
            "mBot, Sonic Pi, Unity) with steps, projects, skills and FAQs.")

    def handle(self, *args, **options):
        created, updated = 0, 0

        for entry in PATHWAYS:
            before = Pathway.objects.filter(name=entry["name"]).values("subtitle", "description").first()
            pathway, was_created = Pathway.objects.update_or_create(
                name=entry["name"],
                defaults={
                    "subtitle": entry["subtitle"],
                    "description": entry["description"],
                    "min_age": entry["min_age"],
                    "max_age": entry["max_age"],
                    "no_experience_needed": entry["no_experience_needed"],
                    "runs_in_browser": entry["runs_in_browser"],
                },
            )
            created += 1 if was_created else 0
            updated += 1 if not was_created else 0
            if before:
                for field in ("subtitle", "description"):
                    if before[field] != entry[field]:
                        pathway.set_translation("nl-be", field, "")
                        pathway.set_translation("fr-be", field, "")
                pathway.save(update_fields=["translations"])

            use_library_image(pathway, "image", "pathways", entry["image"], save=True)

            skills = [Skill.objects.get_or_create(name=name)[0] for name in entry["skills"]]
            pathway.skills.set(skills)

            pathway.steps.all().delete()
            for order, (title, description) in enumerate(entry["steps"], start=1):
                PathwayStep.objects.create(pathway=pathway, order=order, title=title, description=description)

            pathway.projects.all().delete()
            for title, description in entry["projects"]:
                PathwayProject.objects.create(pathway=pathway, title=title, description=description)

            pathway.faqs.all().delete()
            for order, (question, answer) in enumerate(entry["faqs"], start=1):
                FAQ.objects.create(pathway=pathway, question=question, answer=answer, order=order)

        self.stdout.write(self.style.SUCCESS(f"Done. created={created} updated={updated}"))
