# User journeys

One PDF per persona, walking through the site with screenshots, in English (`en/`), Dutch (`nl/`) and French (`fr/`):

| # | Persona | English | Nederlands | Français |
|---|---------|---------|------------|----------|
| 1 | Parent / ouder / parent | [en/1-parent-journey.pdf](en/1-parent-journey.pdf) | [nl/1-ouder.pdf](nl/1-ouder.pdf) | [fr/1-parent.pdf](fr/1-parent.pdf) |
| 2 | Ninja (child's own login) | [en/2-ninja-journey.pdf](en/2-ninja-journey.pdf) | [nl/2-ninja.pdf](nl/2-ninja.pdf) | [fr/2-ninja.pdf](fr/2-ninja.pdf) |
| 3 | Volunteer (mentor) / vrijwilliger / bénévole | [en/3-volunteer-journey.pdf](en/3-volunteer-journey.pdf) | [nl/3-vrijwilliger.pdf](nl/3-vrijwilliger.pdf) | [fr/3-benevole.pdf](fr/3-benevole.pdf) |
| 4 | Champion | [en/4-champion-journey.pdf](en/4-champion-journey.pdf) | [nl/4-champion.pdf](nl/4-champion.pdf) | [fr/4-champion.pdf](fr/4-champion.pdf) |
| 5 | Background-check reviewer / beoordelaar / évaluateur | [en/5-reviewer-journey.pdf](en/5-reviewer-journey.pdf) | [nl/5-beoordelaar.pdf](nl/5-beoordelaar.pdf) | [fr/5-evaluateur.pdf](fr/5-evaluateur.pdf) |
| 6 | Organisation admin / beheerder / administrateur | [en/6-organisation-journey.pdf](en/6-organisation-journey.pdf) | [nl/6-organisatie.pdf](nl/6-organisatie.pdf) | [fr/6-organisation.pdf](fr/6-organisation.pdf) |
| | **Pitch deck**: the journeys plus facts and figures about the development | [en/pitch-deck.pdf](en/pitch-deck.pdf) | [nl/pitchdeck.pdf](nl/pitchdeck.pdf) | (not yet) |

The pitch decks are Slides artifacts on claude.ai (private until shared from their Share menu, which
also exports them to PowerPoint): [English](https://claude.ai/artifact/LDyAfN3vCf5RdS8oxhTDPt),
[Nederlands](https://claude.ai/artifact/RDPZX7Ua73bKdzqvpifhqa). `pitch-deck/<lang>/` is a copy of their
slide files, and `python scripts/build_pitch.py en|nl` renders that copy to the PDFs here (the
screenshots come from `.shots/`, so run the journeys first; icons are drawn as simple line icons). A
change made in the artifact needs copying back into `pitch-deck/` before rebuilding. The last slide's
"ask" is still placeholders in brackets.

Alongside them, **[technical-foundation-and-data-model.pdf](technical-foundation-and-data-model.pdf)**
explains how the site is built, how its data fits together and why: a summary of `DATA_MODEL.md` and
`CLAUDE.md`, with the diagrams taken from `DATA_MODEL.md` as they are. Rebuild it with
`python scripts/build_technical.py` (the same venv as below; the first run downloads Mermaid 11.4.1 from
jsDelivr into `.shots/`, and the build fails if a diagram doesn't render). Its prose is in that script,
so a change to the model or the conventions may need a sentence there too. Its last two chapters,
*Capacity, load and disk* and *Coding standards and quality*, summarise [`CAPACITY.md`](../CAPACITY.md) and
[`CODING_STANDARDS.md`](../CODING_STANDARDS.md) with the charts from `loadtest/charts/` and `quality/charts/`
(embedded when the PDF is built): rebuild it after a new round of measurements.

The screenshots come from the devcontainer's site with the seeded demo data, logged in with the
seeded accounts named on each cover. They are an overview for people, not the help centre:
that's `docs/`.

## Regenerating

From the host (the scripts go through nginx at `https://coolregistration.localhost`, like a real
browser), with the devcontainer stack up and `seed_credentials.csv` in the repo root:

```sh
python3 -m venv /tmp/uj-venv && /tmp/uj-venv/bin/pip install playwright pillow pyotp
cd user-journeys/scripts
for lang in en nl fr; do
  for j in parent ninja volunteer champion reviewer org; do JLANG=$lang /tmp/uj-venv/bin/python j_$j.py; done
  /tmp/uj-venv/bin/python build.py $lang
done
```

- `j_*.py` drive a headless Chrome (Playwright's `channel="chrome"`, so Google Chrome must be
  installed) through one persona each and save screenshots plus a `journey.json` with the English
  captions in `user-journeys/.shots/<lang>/` (gitignored). `JLANG=nl` sets the site's language cookie.
- `build.py <lang>` lays them out into `<lang>/*.pdf`. The Dutch and French captions and cover texts are
  in `nl.py` and `fr.py`, keyed by the step keys the `j_*.py` scripts use, so a new step needs its text
  in both. `JLANG=fr` captures the site in French; a new language needs its locale in `lib.py`, its file
  names in `build.py`'s `NAMES` and a captions module.
- **They change the dev data:** the parent and ninja journeys book real places (sessions 71 and 72
  at Dojo Zonnebeke, removed again first on a rerun), the volunteer journey resets and then marks
  attendance on session 76 at Dojo Westerlo, and the booking mail goes through the Celery workers
  to Mailpit. The seeded IDs used (dojo 51, events 71/72/76, ninja 9, users 352, application 348)
  change when the database is reseeded; adjust them in the scripts.

## Keeping them current

`python3 scripts/check_journeys.py` (from anywhere in the repo, plain Python) compares the code behind
every captured page with `manifest.json`, which fingerprints each persona's views and templates (and the
partials they include) when the PDFs were made. It marks a persona **REVISIT** when that code changed
substantially (a template by 10+ lines, two or more views, or one is gone) and exits 1. Look at whether
what the persona sees or does changed: if so, regenerate its PDFs in en, nl and fr; either way, rerun
`python user-journeys/scripts/manifest.py` inside the workspace container to take the new baseline, and
commit `manifest.json`.

## Screenshot pitfalls

- **Only whole pages.** An htmx endpoint opened on its own URL returns a fragment: no page shell, no
  stylesheet, so the screenshot is unstyled (a child's `/account/ninja/<id>/badges/` and `/avatar/` are two).
  Open the page that loads it and click to that part instead. `Journey.shot` refuses a page without the
  site's stylesheet from `/static/` (Mailpit's pages excepted), so this fails loudly rather than landing in
  a PDF.
- **POST-only actions** (for example a dojo's `manage/lifecycle/`) redirect when opened, so the screenshot
  shows the page they redirect to. Show the page that holds the action's button instead.
- **The Celery workers must be running** for the parent's confirmation-mail step: it waits up to 90 seconds
  for the mail to reach Mailpit. If they're stuck, restart them (CLAUDE.md, "Background jobs").

