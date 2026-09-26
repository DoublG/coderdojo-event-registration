"""The classification of every piece of personal data the site keeps.

DATA_MODEL.md §16, phase 1. Each app declares its models in its own
`privacy.py` (autodiscovered by `privacy.apps.PrivacyConfig`), third-party
models are declared in `privacy/privacy.py`. Every concrete field of every
model must be declared, as personal data (a `FieldPrivacy`) or as not
personal: `privacy.tests` fails on a field nobody made a decision about.

The later phases (the register of processing activities, export, retention
and erasure) are built on this registry only, so a field classified here is
covered by all of them.

    register(
        Registration,
        purpose="Signing a child up for a session",
        legal_basis=LegalBasis.CONTRACT,
        retention="registration",
        seen_by="The family, the dojo team",
        subjects={Subject.CHILD: "ninja"},
        fields={
            "ninja": keep(Category.CHILD, "points at the anonymised child"),
            ("attended", "created_at"): keep(Category.CHILD, "session numbers"),
        },
        not_personal=["id", "event"],
    )

`subjects` says whose row it is, for a person's export (`privacy.export`):
a lookup to the account, to a child, or a field holding the account's email
address (`Subject`).

A tuple key gives several fields the same classification. There is no
default for a model's fields on purpose: a new field always needs its own
decision.
"""

from dataclasses import dataclass, field, replace

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist, FieldError, ImproperlyConfigured
from django.db.models import TextChoices


class Category(TextChoices):
    IDENTITY = "identity", "Identity and contact details"
    CHILD = "child", "About a child"
    SPECIAL = "special", "Special category (art. 9): health"
    CRIMINAL = "criminal", "Criminal records (art. 10): background checks"
    PROFILING = "profiling", "Profiling: engagement and mail targeting"
    PUBLIC_PROFILE = "public_profile", "Shown on the public site by choice"
    CONTACT_PUBLIC = "contact_public", "Published contact details"
    SECURITY = "security", "Security: passwords, tokens, login data"


class LegalBasis(TextChoices):
    CONTRACT = "contract", "Contract (art. 6.1.b)"
    LEGITIMATE_INTEREST = "legitimate_interest", "Legitimate interest (art. 6.1.f)"
    CONSENT = "consent", "Consent (art. 6.1.a)"
    LEGAL_OBLIGATION = "legal_obligation", "Legal obligation (art. 6.1.c)"


class Subject(TextChoices):
    """Whose row it is, for a person's export (and later their erasure):
    `subjects` maps each to a lookup from the model."""

    # A lookup to the account (accounts.User), e.g. "user" or "pk".
    ACCOUNT = "account", "An account"
    # A lookup to a child (accounts.Ninja), e.g. "ninja".
    CHILD = "child", "A child"
    # A field holding the account's email address.
    EMAIL = "email", "An email address"


class Erasure(TextChoices):
    # The value is emptied (its field's empty value or default); on a
    # required link to the person, the row goes.
    DELETE = "delete", "Delete"
    # Replaced by `replacement` ("{pk}" is the row's id).
    ANONYMISE = "anonymise", "Anonymise"
    # Kept, for the `reason` given.
    KEEP = "keep", "Keep"


# Retention rules by name: what each keeps and for how long. The nightly job
# (privacy.retention, periods in settings) applies "account", "audit_log" and
# "login_session"; the other periods still need legal input (DATA_MODEL.md
# §16, open points).
RETENTION_RULES = {
    "account": "Until two years after the last login: reminder mails 30 and 7 days before, then erased.",
    "organisation_role": "While the organisation role is held.",
    "child": "Until N years after the child's last session, or after they turn 18.",
    "registration": "The link to the child is anonymised N years after the session; the numbers stay.",
    "engagement": "Rebuilt every night over the last year; stage changes kept N months.",
    "team": "While on the team; a membership that went dormant is kept for past sessions' teams for N years.",
    "team_attendance": "As long as the insurance needs the record of who was there.",
    "application": "N years after the decision.",
    "background_check": "The document is deleted at the decision; the decisions as long as the legal rules say.",
    "mail_content": "Subject, body and address of a mail cleared after 12 months; the row stays for statistics.",
    "mail_log": "Bounce records and handled bounce-mailbox messages removed after 12 months.",
    "consent_proof": "As long as the account exists, then as long as the consent may have to be proven.",
    "suppression": "As long as the address must not be mailed again.",
    "notification": "Read notifications removed after N months.",
    "published": "While shown on the site; removed on request.",
    "login_session": "Until the login session expires.",
    "admin_log": "N years, for tracing changes made by hand.",
    "audit_log": "Until two years after the last login of the account it's about or was made by; "
    "two years after the entry when no account is behind it.",
    "task_result": "Until the task result expires.",
    "erasure_log": "As long as backups made before the erasure exist.",
}

_UNSET = object()


@dataclass(frozen=True)
class Computed:
    """A replacement worked out per row at erasure (`function(obj)`), e.g. an
    unusable password; `description` is what the register shows."""

    description: str
    function: object

    def __repr__(self):
        return self.description


@dataclass(frozen=True)
class FieldPrivacy:
    """What one field holds about a person and what happens to it.
    `purpose`, `legal_basis`, `retention` and `seen_by` default to the
    model's."""

    category: Category
    on_erasure: Erasure = Erasure.DELETE
    replacement: object = _UNSET
    reason: str = ""
    export: bool = True
    purpose: str = ""
    legal_basis: str = ""
    retention: str = ""
    seen_by: str = ""


def personal(category, *, export=True, **kwargs):
    """Personal data that is emptied (or its row deleted) on erasure."""
    return FieldPrivacy(category, Erasure.DELETE, export=export, **kwargs)


def anonymise(category, replacement, *, export=True, **kwargs):
    """Personal data replaced on erasure; `replacement` may use "{pk}", or be
    a `Computed` worked out per row."""
    return FieldPrivacy(category, Erasure.ANONYMISE, replacement=replacement, export=export, **kwargs)


def keep(category, reason, *, export=True, **kwargs):
    """Personal data kept on erasure, for `reason`."""
    return FieldPrivacy(category, Erasure.KEEP, reason=reason, export=export, **kwargs)


@dataclass(frozen=True)
class ModelPrivacy:
    model: type
    purpose: str
    legal_basis: str
    retention: str
    seen_by: str
    fields: dict = field(default_factory=dict)  # name -> FieldPrivacy
    not_personal: frozenset = frozenset()
    not_personal_reason: str = ""
    subjects: dict = field(default_factory=dict)  # Subject -> lookup
    # The boolean field saying whether a row's public_profile fields are on
    # the public site: an erasure with keep_visible keeps them only then.
    visible_when: str = ""

    @property
    def label(self):
        return self.model._meta.label

    @property
    def is_personal(self):
        return bool(self.fields)


class Registry:
    """The declarations; `site` below is the one every privacy.py fills."""

    def __init__(self):
        self._entries = {}

    def register(
        self,
        model,
        *,
        purpose="",
        legal_basis="",
        retention="",
        seen_by="",
        fields=None,
        not_personal=(),
        subjects=None,
        visible_when="",
    ):
        """Declare a model's personal data (see the module docstring).
        Mistakes in a declaration (an unknown field, a missing reason) raise
        right away; fields left out are reported by `unclassified()`."""
        label = model._meta.label

        def fail(message):
            raise ImproperlyConfigured(f"privacy: {label}: {message}")

        if model in self._entries:
            fail("registered twice")
        resolved = {}
        for names, spec in (fields or {}).items():
            for name in (names,) if isinstance(names, str) else names:
                if name in resolved:
                    fail(f"{name} is classified twice")
                spec = replace(
                    spec,
                    purpose=spec.purpose or purpose,
                    legal_basis=spec.legal_basis or legal_basis,
                    retention=spec.retention or retention,
                    seen_by=spec.seen_by or seen_by,
                )
                if spec.category not in Category.values:
                    fail(f"{name}: unknown category {spec.category!r}")
                if not spec.purpose:
                    fail(f"{name}: no purpose")
                if not spec.seen_by:
                    fail(f"{name}: no seen_by")
                if spec.legal_basis not in LegalBasis.values:
                    fail(f"{name}: unknown legal basis {spec.legal_basis!r}")
                if spec.retention not in RETENTION_RULES:
                    fail(f"{name}: unknown retention rule {spec.retention!r}")
                if spec.on_erasure == Erasure.ANONYMISE and spec.replacement is _UNSET:
                    fail(f"{name}: anonymised without a replacement")
                if spec.on_erasure == Erasure.KEEP and not spec.reason:
                    fail(f"{name}: kept on erasure without a reason")
                resolved[name] = spec

        not_personal = frozenset(not_personal)
        for name in [*resolved, *not_personal, *([visible_when] if visible_when else [])]:
            try:
                model._meta.get_field(name)
            except FieldDoesNotExist:
                fail(f"no field {name!r}")
        if both := not_personal & resolved.keys():
            fail(f"{', '.join(sorted(both))} both personal and not personal")
        subjects = dict(subjects or {})
        for subject, lookup in subjects.items():
            if subject not in Subject.values:
                fail(f"unknown subject {subject!r}")
            try:
                model._base_manager.filter(**{f"{lookup}__isnull": True})
            except FieldError:
                fail(f"subject {subject}: no lookup {lookup!r}")

        self._entries[model] = ModelPrivacy(
            model,
            purpose,
            legal_basis,
            retention,
            seen_by,
            resolved,
            not_personal,
            subjects=subjects,
            visible_when=visible_when,
        )
        return self._entries[model]

    def register_not_personal(self, model, reason):
        """Declare a whole model as holding no personal data, with the reason."""
        if not reason:
            raise ImproperlyConfigured(f"privacy: {model._meta.label}: not personal without a reason")
        entry = self.register(model, not_personal=[f.name for f in classifiable_fields(model)])
        self._entries[model] = replace(entry, not_personal_reason=reason)
        return self._entries[model]

    def get(self, model):
        return self._entries.get(model)

    def registered(self):
        """Every declaration, in model label order."""
        return sorted(self._entries.values(), key=lambda entry: entry.label)

    def unclassified(self, models=None):
        """`app_label.Model.field` for every field without a decision, and
        `app_label.Model` for every model without a declaration (of
        `models`, by default every installed one)."""
        missing = []
        for model in classifiable_models() if models is None else models:
            entry = self._entries.get(model)
            if entry is None:
                missing.append(model._meta.label)
                continue
            for model_field in classifiable_fields(model):
                if model_field.name not in entry.fields and model_field.name not in entry.not_personal:
                    missing.append(f"{model._meta.label}.{model_field.name}")
        return missing


site = Registry()
register = site.register
register_not_personal = site.register_not_personal
get = site.get
registered = site.registered
unclassified = site.unclassified


def classifiable_fields(model):
    """The fields that need a decision: the concrete ones and the model's own
    many-to-many fields (their auto-created tables hold nothing else)."""
    return [*model._meta.concrete_fields, *model._meta.local_many_to_many]


def classifiable_models():
    """Every installed model with its own table: proxies share their
    model's, auto-created many-to-many tables are covered by the field."""
    return [model for model in apps.get_models() if not model._meta.proxy and not model._meta.auto_created]
