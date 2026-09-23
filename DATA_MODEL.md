# Data model

How the CoderDojo Belgium site's data fits together, one diagram per area.
This is for developers. The end-user help centre lives in `docs/`, and the
conventions and gotchas live in `CLAUDE.md`. The diagrams are
[Mermaid](https://mermaid.js.org/), which GitHub and VS Code's Markdown
preview render inline.

Each diagram shows only the fields that carry meaning. Plain text and
display fields (descriptions, taglines, photos, …) are left out; the models
in each app's `models.py` have the full field lists. If you change a model,
update its diagram in the same change.

**Contents**

1. [Overview](#1-overview)
2. [Accounts and roles](#2-accounts-and-roles)
3. [Dojos, team pages and admin access](#3-dojos-team-pages-and-admin-access)
4. [Events, registrations and attendance](#4-events-registrations-and-attendance)
5. [Awards](#5-awards)
6. [Applications and background checks](#6-applications-and-background-checks)
7. [Learning pathways and content](#7-learning-pathways-and-content)
8. [Notifications](#8-notifications)
9. [Geo reference data](#9-geo-reference-data)

---

## 1. Overview

The main entities and how they connect, grouped by the Django app that owns them.

```mermaid
flowchart LR
    subgraph accounts
        User
        DojoOwner
        HelperAccount
        Guardian
        ChildAccount
        Participant
    end
    subgraph dojos
        Dojo
        Mentor
    end
    subgraph events
        Event
        Registration
        Award
    end
    subgraph applications
        DojoApplication
        MentorApplication
    end
    subgraph pathways
        Pathway
    end
    subgraph geo
        Municipality
        AdministrativeBoundary
    end

    User -. "is-a (MTI)" .-> DojoOwner & HelperAccount & Guardian & ChildAccount
    DojoOwner -- owns --> Dojo
    Mentor -- "team profile at" --> Dojo
    Mentor -. "login (at most one)" .-> DojoOwner & HelperAccount & Guardian & ChildAccount
    Guardian -- "parent of" --> Participant
    Participant -. "optional login" .-> ChildAccount
    Dojo -- runs --> Event
    Registration -- for --> Event
    Registration -- of --> Participant
    Registration -. "worked on" .-> Pathway
    Participant -- earns --> Award
    DojoApplication -- provisions --> DojoOwner
    MentorApplication -- provisions --> HelperAccount
    MentorApplication -. "for" .-> Dojo
    Dojo -. located in .-> Municipality & AdministrativeBoundary
```

---

## 2. Accounts and roles

`accounts.User` is the login. Each role is a **multi-table-inheritance
child** of it, not a `role` field, and one `User` row can hold several roles
at once. `accounts.provisioning.attach_role` adds a role to an existing
account. A child role row shares the `User`'s primary key, so
`helperaccount.pk == user.pk`.

A `Participant` (a child attending sessions) is **not** a user. It gets a
login (`ChildAccount`) only if its guardian opts it in.

```mermaid
classDiagram
    direction TB
    class User {
        +username
        +email
        +must_change_password
        +background_check_required
        +background_check_expires_at
        +background_check_valid() bool
    }
    class DojoOwner {
        background-checked
        admin-provisioned
    }
    class HelperAccount {
        background-checked
        admin-provisioned
    }
    class Guardian {
        +phone
        self-service sign-up
    }
    class ChildAccount {
        opt-in by guardian
    }
    class Participant {
        +name
        +date_of_birth
        +experience_level
        +allergies_notes
        +member_since
        +age() int
    }

    User <|-- DojoOwner
    User <|-- HelperAccount
    User <|-- Guardian
    User <|-- ChildAccount

    Guardian "0..1" --> "*" Participant : children
    Participant "0..1" --> "0..1" ChildAccount : account
    Participant "*" --> "0..1" Dojo : home_dojo
```

Which role does what:

| Role | Created by | Background check | Lands on after login |
|---|---|---|---|
| `DojoOwner` | admin approval of a `DojoApplication` | required (gates login) | first accessible dojo's dashboard |
| `HelperAccount` | admin approval of a `MentorApplication` | required (gates login) | first accessible dojo's dashboard |
| `Guardian` | self-service (`register_guardian`, `link_guardian_role`) | none | their family page |
| `ChildAccount` | guardian opts a child in | none | the child's page |

---

## 3. Dojos, team pages and admin access

`Mentor` is a public team-page profile at one dojo. It may point to the
login of the person behind it, through at most one of four account links
(enforced in `Mentor.clean()`).

- **Owner = Lead Coach.** `Dojo.save()` calls `Dojo.sync_lead_coach()`, so
  every owned dojo has exactly one `LEAD_COACH` Mentor, linked to its
  current owner. When ownership changes, the previous owner's profile
  becomes a plain volunteer profile. It isn't deleted, so past
  `Event.mentors` links keep their history.
- **Owners and helpers can be linked to several dojos.** `owner_account` and
  `helper_account` are ForeignKeys, with one profile per dojo enforced by a
  unique constraint on each. `guardian_account` and `child_account` are
  one-to-one.

```mermaid
erDiagram
    DOJO_OWNER ||--o{ DOJO : "owns (Dojo.owner)"
    DOJO ||--o{ MENTOR : "mentors"
    DOJO_OWNER |o--o{ MENTOR : "owner_account (Lead Coach, one per dojo)"
    HELPER_ACCOUNT |o--o{ MENTOR : "helper_account (one per dojo)"
    GUARDIAN |o--o| MENTOR : "guardian_account"
    CHILD_ACCOUNT |o--o| MENTOR : "child_account"
    MUNICIPALITY |o--o{ DOJO : "municipality"
    ADMINISTRATIVE_BOUNDARY |o--o{ DOJO : "province"

    DOJO {
        bigint id PK
        string name
        string address
        point location "geocoded from address"
        bigint owner_id FK "nullable"
        bigint municipality_id FK
        bigint province_id FK "set from location"
        int min_age
        int max_age
    }
    MENTOR {
        bigint id PK
        bigint dojo_id FK "blank for board members"
        string role "lead_coach, champion, ninja, volunteer, board"
        bigint owner_account_id FK "LEAD_COACH only"
        bigint helper_account_id FK
        bigint guardian_account_id FK "unique"
        bigint child_account_id FK "unique"
        bool is_public "shown on team pages"
    }
```

### Who can use a dojo's admin area

`dojos/access.py` resolves the viewer's role at a dojo, and each role maps
to a set of capabilities. With no role at all the dojo gives a **404**; a
role that lacks the view's capability gets a **403**.

```mermaid
flowchart TD
    R[Request to /dojos/ID/...] --> A{Logged in?}
    A -- no --> L[Redirect to login]
    A -- yes --> O{"Dojo.owner == user?"}
    O -- yes --> OWNER[Role: OWNER]
    O -- no --> H{"Mentor at this dojo with<br/>helper_account == user?"}
    H -- yes --> HELPER[Role: HELPER]
    H -- no --> N404[404 Not Found]
    OWNER --> C{"Capability in<br/>ROLE_CAPABILITIES[role]?"}
    HELPER --> C
    C -- yes --> OK[Render the page]
    C -- no --> N403[403 Forbidden]
```

| Capability | Gates | OWNER | HELPER (today) |
|---|---|:-:|:-:|
| *(any role)* | dashboard, events list, notification bell | ✓ | ✓ |
| `TAKE_ATTENDANCE` | attendance pages, marking present/absent | ✓ | ✓ |
| `MANAGE_EVENTS` | create/edit events, change status | ✓ | ✓ |
| `EDIT_SETTINGS` | dojo profile settings | ✓ | ✓ |

To restrict helpers, remove entries from `ROLE_CAPABILITIES[HELPER]`.
Guardian- and child-linked mentor profiles never get admin access, because
those accounts aren't background-checked.

---

## 4. Events, registrations and attendance

```mermaid
erDiagram
    DOJO ||--o{ EVENT : "runs"
    EVENT ||--o{ REGISTRATION : "registration_set"
    PARTICIPANT ||--o{ REGISTRATION : "signs up via"
    PATHWAY |o--o{ REGISTRATION : "worked on"
    EVENT }o--o{ MENTOR : "mentors (M2M)"

    EVENT {
        bigint id PK
        bigint dojo_id FK
        string name
        string status "draft, open, closed"
        datetime start_time "same day as end_time"
        datetime end_time
        int places
        point location
        string venue_name
        int min_age
        int max_age
    }
    REGISTRATION {
        bigint id PK
        bigint event_id FK "unique with participant"
        bigint participant_id FK
        bool waiting_list
        int position "first-come queue"
        bool attended "null = not marked"
        bigint pathway_id FK "nullable"
    }
```

- **Places:** `Event.places_left` = `places` − confirmed registrations
  (those with `waiting_list=False`). When a confirmed place is cancelled,
  the next person on the waiting list is promoted and the dojo owner is
  notified.
- **Attendance:** `Registration.attended` has three states: `None` (not
  marked yet), `True` (present), `False` (absent). Only confirmed
  registrations can be marked.

### Event status

The owner sets any status directly (`dojo_event_set_status`); it isn't a
one-way lifecycle. Existing registrations are kept whatever the status.

```mermaid
stateDiagram-v2
    [*] --> draft : created
    draft --> open : Publish
    open --> closed : Close registrations
    closed --> open : Reopen registrations
    open --> draft : Back to draft
    closed --> draft : Back to draft
    draft --> closed

    draft : draft<br/>hidden from the public site
    open : open<br/>public, sign-ups accepted
    closed : closed<br/>public, no new sign-ups
```

---

## 5. Awards

`Award` uses the same multi-table-inheritance pattern as the account
roles. There are two separate kinds: a milestone reached by a repeat count
(for example the attendance wristbands), and a one-off badge.

```mermaid
classDiagram
    class Award {
        +name
        +description
        +icon
    }
    class MilestoneAward {
        +threshold
    }
    class BadgeAward {
        +criteria
    }
    class ParticipantAward {
        +earned_date
        +progress_current
        +progress_total
    }
    Award <|-- MilestoneAward
    Award <|-- BadgeAward
    Participant "1" --> "*" ParticipantAward : awards
    Award "1" --> "*" ParticipantAward : participant_awards
```

---

## 6. Applications and background checks

Both application types mix in `BackgroundCheckMixin`, which tracks Belgium's
Article 596.2 criminal-record-extract requirement. When a check is
validated, the uploaded document is **deleted** and only the decision and
its expiry are kept.

```mermaid
erDiagram
    USER |o--o{ DOJO_APPLICATION : "applicant_account (if logged in)"
    USER |o--o{ MENTOR_APPLICATION : "applicant_account (if logged in)"
    DOJO_OWNER |o--o{ DOJO_APPLICATION : "provisioned_owner (one per dojo started)"
    HELPER_ACCOUNT |o--o{ MENTOR_APPLICATION : "provisioned_helper (one per dojo)"
    DOJO |o--o{ MENTOR_APPLICATION : "dojo (blank = any)"

    DOJO_APPLICATION {
        bigint id PK
        string applicant_name
        string applicant_email
        string area
        string status "pending, approved, rejected"
        string background_check_status
        datetime background_check_expires_at
        uuid background_check_token "emailed upload link"
        file background_check_document "private, deleted on validation"
    }
    MENTOR_APPLICATION {
        bigint id PK
        string applicant_name
        string applicant_email
        bigint dojo_id FK
        string role "volunteer_mentor, other"
        string status "pending, approved, rejected"
        string background_check_status
        datetime background_check_expires_at
    }
```

### Background check lifecycle

```mermaid
stateDiagram-v2
    [*] --> not_requested
    not_requested --> requested : admin "Request background check"
    requested --> submitted : applicant uploads (emailed link)
    submitted --> validated : reviewer validates<br/>(document deleted, expiry = now + 365 days)
    submitted --> rejected : reviewer rejects
    validated --> requested : renewal requested (expiring/expired)
    rejected --> requested : request again
```

### From approval to a login

```mermaid
flowchart TD
    A[Admin approves application] --> V{Valid background check?}
    V -- no --> S[Skipped]
    V -- yes --> E{applicant_account set?<br/>applied while logged in}
    E -- yes --> P["attach_role(existing account)<br/>+ 'new role' email"]
    E -- no --> N["provision_account()<br/>random temp password emailed<br/>must_change_password = True"]
    P --> X["Copy background-check expiry onto the account<br/>(keeps the later of old and new)"]
    N --> X
    X --> K{MentorApplication with a dojo?}
    K -- yes --> M["Create Mentor at that dojo<br/>(helper_account, volunteer, not public)<br/>unless one already exists there"]
    K -- no --> D[Done]
    M --> D
```

After approval, **the account** gates login: once
`background_check_valid` is false, `BackgroundCheckMiddleware` blocks every
request and sends the user to `renew_background_check`. The renewal is
uploaded against the account's most recently submitted application.

---

## 7. Learning pathways and content

`pathways` is a read-mostly catalogue with no enrolment state. The only
place it's linked to a child is `Registration.pathway`. The `content`
models are each optionally scoped to one dojo, event or pathway, or
site-wide when the scoping key is blank.

```mermaid
erDiagram
    PATHWAY ||--o{ PATHWAY_STEP : "steps (ordered)"
    PATHWAY ||--o{ PATHWAY_PROJECT : "projects"
    PATHWAY }o--o{ SKILL : "skills (M2M)"
    DOJO |o--o{ FAQ : "scoped to"
    EVENT |o--o{ FAQ : "scoped to"
    PATHWAY |o--o{ FAQ : "scoped to"
    DOJO |o--o{ TESTIMONIAL : "scoped to (blank = site-wide)"
    DOJO ||--o{ ANNOUNCEMENT : "posts"

    PATHWAY {
        bigint id PK
        string name
        int min_age
        int max_age
        bool no_experience_needed
        bool runs_in_browser
    }
    PATHWAY_STEP {
        bigint pathway_id FK
        int order
        string title
    }
    FAQ {
        bigint dojo_id FK "nullable"
        bigint event_id FK "nullable"
        bigint pathway_id FK "nullable"
        string question
        int order
    }
    TESTIMONIAL {
        bigint dojo_id FK "nullable"
        string quote
        string author
    }
    ANNOUNCEMENT {
        bigint dojo_id FK
        date date
        string text
    }
```

---

## 8. Notifications

Each `Notification` row belongs to one recipient, so read state is per
user. An event that concerns several people creates one row per recipient.
Always create notifications through `notifications.services.notify()`: it
writes the row, then pushes the updated bell over the WebSocket channel
layer, on a best-effort basis.

```mermaid
erDiagram
    USER ||--o{ NOTIFICATION : "recipient"
    DOJO |o--o{ NOTIFICATION : "dojo (admin bell filter)"

    NOTIFICATION {
        bigint id PK
        bigint recipient_id FK
        bigint dojo_id FK "nullable"
        string text
        string url
        datetime created_at
        bool read
    }
```

```mermaid
sequenceDiagram
    participant V as View (e.g. register_helper)
    participant S as notify()
    participant DB as MySQL
    participant CL as Channel layer (Redis)
    participant C as NotificationConsumer
    participant B as Browser (admin page)

    V->>S: notify(recipient, text, url, dojo)
    S->>DB: INSERT Notification
    S-)CL: group_send("notifications_user_{id}")
    Note over S,CL: failures are swallowed (fail-open)
    CL-)C: notification.push
    C->>DB: re-query this dojo's bell
    C-)B: _notification_bell.html (hx-swap-oob)
```

---

## 9. Geo reference data

Reference data only (seeded by `seed_geo`), with no URLs of its own. A
dojo's `province` is derived from its geocoded `location`: a
point-in-polygon lookup against `AdministrativeBoundary`, falling back to
the nearest boundary. Distance searches always use
`geo.functions.DistanceSphere` (MySQL `ST_Distance_Sphere`).

```mermaid
erDiagram
    MUNICIPALITY |o--o{ DOJO : "municipality"
    ADMINISTRATIVE_BOUNDARY |o--o{ DOJO : "province"

    MUNICIPALITY {
        bigint id PK
        string postal_code
        string name
        point center
    }
    ADMINISTRATIVE_BOUNDARY {
        bigint id PK
        string kind "e.g. province"
        string name
        multipolygon boundary
    }
```
