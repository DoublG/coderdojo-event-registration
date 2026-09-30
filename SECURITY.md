# Security policy

This repository is the registration site of [CoderDojo Belgium vzw](https://coderdojobelgium.be): dojo
discovery, event registration, family accounts and volunteer onboarding. It holds personal data about
children and their families, health notes, and the outcome of volunteers' background checks, so we take
reports about its security seriously and are grateful for them.

## Supported versions

Only the current `main` branch is supported: it's what the live site runs. There are no releases or
older versions that receive fixes.

## Reporting a vulnerability

**Please don't report a vulnerability in a public issue, pull request or discussion.**

Report it privately, in one of two ways:

1. **Preferred:** on GitHub, open the repository's **Security** tab and choose **Report a vulnerability**.
   This creates a private advisory that only the maintainers can see, and we can work on the fix with you
   there.
2. By email to **erik@woidt.be**, with "Security" in the subject.

Please include:

- what the problem is and where (a page, URL, API endpoint or file in this repository);
- the steps to reproduce it, or a proof of concept;
- what an attacker could do with it, as far as you know (for example: whose data they could see or change);
- whether you have seen, kept or shared anyone's personal data while finding it (see below).

## What to expect

CoderDojo Belgium is run by volunteers, but a security report goes before other work.

| Step | When |
|---|---|
| We confirm we received your report | Within 3 working days |
| We tell you our assessment (whether we can reproduce it, how severe it is here) | Within 7 days |
| We fix it | Critical: 24–48 hours. High: 7 days. Medium: 30 days. Low: with the next regular update |

The severities are the ones in [`MAINTENANCE.md`](MAINTENANCE.md#triage); "critical" includes anything
that gives access to children's data, health notes or background-check documents. We'll keep you
informed while we work on it, tell you when it's fixed, and credit you in the advisory if you'd like
that. If personal data may have leaked, we also have legal duties towards the Belgian Data Protection
Authority and the families concerned, which we follow as described in `MAINTENANCE.md`.

Please give us the chance to fix it before you tell anyone else about it.

## Scope

In scope:

- the code in this repository;
- the live registration site that runs it.

Out of scope:

- denial-of-service attacks, load tests, spam and social engineering of our volunteers or families;
- CoderDojo Belgium's other websites and services, and the infrastructure of our hosting provider
  (report those to them);
- vulnerabilities in a dependency that aren't reachable in this project (please report those upstream;
  we track them with `pip-audit`, Dependabot and CodeQL);
- findings from automated scanners without a demonstrated impact, and missing security headers alone.

## Testing safely

The live site contains real data about children. Please:

- **test against your own copy wherever you can.** The repository has a complete development setup with
  demo data (`.devcontainer/`, see the README), which is the best place to try things out;
- on the live site, only use accounts you created yourself, and never access, change or delete other
  people's data beyond the minimum needed to show the problem;
- if you do come across someone else's personal data, stop, don't keep a copy, and tell us in your
  report;
- don't send mail to other users or overload the site.

If you follow these rules and report in good faith, we won't take legal action against you for your
research, and we'll treat your report in confidence.
