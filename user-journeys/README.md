# User journeys

One PDF per persona, walking through the site with screenshots, in English (`en/`) and Dutch (`nl/`):

| # | Persona | English | Nederlands |
|---|---------|---------|------------|
| 1 | Parent / ouder | [en/1-parent-journey.pdf](en/1-parent-journey.pdf) | [nl/1-ouder.pdf](nl/1-ouder.pdf) |
| 2 | Ninja (child's own login) | [en/2-ninja-journey.pdf](en/2-ninja-journey.pdf) | [nl/2-ninja.pdf](nl/2-ninja.pdf) |
| 3 | Volunteer (mentor) / vrijwilliger | [en/3-volunteer-journey.pdf](en/3-volunteer-journey.pdf) | [nl/3-vrijwilliger.pdf](nl/3-vrijwilliger.pdf) |
| 4 | Champion | [en/4-champion-journey.pdf](en/4-champion-journey.pdf) | [nl/4-champion.pdf](nl/4-champion.pdf) |
| 5 | Background-check reviewer / beoordelaar | [en/5-reviewer-journey.pdf](en/5-reviewer-journey.pdf) | [nl/5-beoordelaar.pdf](nl/5-beoordelaar.pdf) |
| 6 | Organisation admin / beheerder | [en/6-organisation-journey.pdf](en/6-organisation-journey.pdf) | [nl/6-organisatie.pdf](nl/6-organisatie.pdf) |

The screenshots come from the devcontainer's site with the seeded demo data, logged in with the
seeded accounts named on each cover. They are an overview for people, not the help centre:
that's `docs/`.

## Regenerating

From the host (the scripts go through nginx at `https://coolregistration.localhost`, like a real
browser), with the devcontainer stack up and `seed_credentials.csv` in the repo root:

```sh
python3 -m venv /tmp/uj-venv && /tmp/uj-venv/bin/pip install playwright pillow pyotp
cd user-journeys/scripts
for lang in en nl; do
  for j in parent ninja volunteer champion reviewer org; do JLANG=$lang /tmp/uj-venv/bin/python j_$j.py; done
  /tmp/uj-venv/bin/python build.py $lang
done
```

- `j_*.py` drive a headless Chrome (Playwright's `channel="chrome"`, so Google Chrome must be
  installed) through one persona each and save screenshots plus a `journey.json` with the English
  captions in `user-journeys/.shots/<lang>/` (gitignored). `JLANG=nl` sets the site's language cookie.
- `build.py <lang>` lays them out into `<lang>/*.pdf`. The Dutch captions and cover texts are in
  `nl.py`, keyed by the step keys the `j_*.py` scripts use, so a new step needs its Dutch text there too.
- **They change the dev data:** the parent and ninja journeys book real places (sessions 71 and 72
  at Dojo Zonnebeke, removed again first on a rerun), the volunteer journey resets and then marks
  attendance on session 76 at Dojo Westerlo, and the booking mail goes through the Celery workers
  to Mailpit. The seeded IDs used (dojo 51, events 71/72/76, ninja 9, users 352, application 348)
  change when the database is reseeded; adjust them in the scripts.
