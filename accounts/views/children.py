"""A child's pages for the family: adding a child, a child's page and details,
the avatar (also the child's own login's) and the badges."""

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from core.image_library import use_library_image

from .. import home_dojo
from ..consent import consent_fields
from ..forms import (
    AddChildForm,
    ChildAvatarForm,
    EditChildForm,
)
from ..models import Guardianship
from ..template_avatars import TEMPLATE_KID_AVATARS
from .child_logins import _login_card_context
from .common import BADGES_PAGE_SIZE, _get_own_ninja
from .family import _children_context


@login_required
def add_ninja(request):
    """The "Register another child" form on the account page
    (accounts/partials/_add_child.html, AddChildForm) — posts here via htmx
    and swaps in the freshly rendered list, plus the form itself out of
    band: a fresh one after adding, or the posted one with its errors."""
    if request.user.is_ninja:
        raise Http404
    guardian = request.user
    form = AddChildForm(request.POST or None, guardian=guardian)
    if request.method == "POST" and form.is_valid():
        ninja = form.save(commit=False)
        _set_icon(ninja, form.cleaned_data["icon"])
        with transaction.atomic():  # a child never exists without a guardian
            ninja.save()
            Guardianship.objects.create(guardian=guardian, ninja=ninja, **consent_fields(form.cleaned_data["consent"]))
        form = AddChildForm(guardian=guardian)
    return render(
        request,
        "accounts/partials/_children_list.html",
        {
            "guardian": guardian,
            "children": _children_context(guardian),
            "add_child_form": form,
            "add_child_oob": True,
        },
    )


def _badges_queryset(child):
    return child.badges.select_related("badge").order_by("id")


@login_required
def ninja_detail(request, ninja_id):
    child = _get_own_ninja(request, ninja_id, allow_self=True)
    now = timezone.now()
    history = (
        child.registration_set.filter(event__start_time__lt=now)
        .select_related("event", "event__dojo")
        .prefetch_related("event__team__user", "pathways")
        .order_by("-event__start_time")
    )
    upcoming = (
        child.registration_set.filter(event__start_time__gte=now)
        .select_related("event", "event__dojo")
        .order_by("event__start_time")
    )
    belt_history = list(
        child.belts.select_related(
            "belt",
            "awarded_by",
            "awarded_as_membership__user",
            "awarded_as_membership__dojo",
        )
    )

    # Initial batch for the Badges carousel — further batches are
    # lazy-loaded over htmx as it's scrolled, against award_widget below
    # (same approach as the homepage's "Upcoming sessions" carousel).
    badges_page = Paginator(_badges_queryset(child), BADGES_PAGE_SIZE).get_page(1)
    badges_next_page_url = None
    if badges_page.has_next():
        badges_next_page_url = (
            f"{reverse('ninja_badges', kwargs={'ninja_id': child.id})}?page={badges_page.next_page_number()}"
        )

    return render(
        request,
        "accounts/child_detail.html",
        {
            "child": child,
            "history": history,
            "upcoming": upcoming,
            "can_edit": child.guardianships.filter(guardian=request.user).exists(),
            "can_pick_avatar": child.account_id == request.user.pk,
            "badges": badges_page.object_list,
            "badges_next_page_url": badges_next_page_url,
            # Current belt = the highest in the history (newest first).
            "belt_history": belt_history,
            "current_belt": child.current_belt,
            **_login_card_context(child),
        },
    )


def _set_icon(child, icon):
    """Point the child's photo at the picked standard avatar — linked from
    the shared image library (core.image_library), never copied. An
    unknown/empty choice leaves the photo as it was."""
    if icon in dict(TEMPLATE_KID_AVATARS):
        use_library_image(child, "photo", "ninjas", icon)


@login_required
def edit_ninja(request, ninja_id):
    """Click-to-edit for the child detail page's header (see
    partials/_child_header_display.html) — GET swaps the display header
    for a small inline form over htmx; POST saves it and swaps back.
    Guardians only; a ninja's own login can't edit its profile."""
    child = _get_own_ninja(request, ninja_id)
    form = EditChildForm(request.POST or None, instance=child)
    if request.method == "POST" and form.is_valid():
        child = form.save(commit=False)
        home_dojo.set_home_dojo(child, form.cleaned_data["home_dojo"])
        _set_icon(child, form.cleaned_data["icon"])
        child.save()
        return render(
            request,
            "accounts/partials/_child_header_display.html",
            {
                "child": child,
                "can_edit": True,
            },
        )
    return render(request, "accounts/partials/_child_header_edit.html", {"child": child, "form": form})


@login_required
def ninja_avatar(request, ninja_id):
    """A child's own login picks its avatar on its own page, over htmx like
    edit_ninja: GET swaps the header for the picker, POST saves and swaps
    back. Only the standard avatars (ChildAvatarForm); uploading a photo is
    the guardian's. The guardians may use it too, though their edit form
    has the same choice."""
    child = _get_own_ninja(request, ninja_id, allow_self=True)
    form = ChildAvatarForm(child, request.POST or None)
    if request.method == "POST" and form.is_valid():
        _set_icon(child, form.cleaned_data["icon"])
        child.save(update_fields=["photo"])
        return render(
            request,
            "accounts/partials/_child_header_display.html",
            {
                "child": child,
                "can_edit": child.guardianships.filter(guardian=request.user).exists(),
                "can_pick_avatar": child.account_id == request.user.pk,
            },
        )
    return render(request, "accounts/partials/_child_avatar_picker.html", {"child": child, "form": form})


@login_required
def ninja_badges(request, ninja_id):
    """Lazy-loaded batches for the child detail page's Badges carousel —
    returns just the next batch of cards (see partials/_badges_page.html),
    triggered by htmx as the carousel is scrolled."""
    child = _get_own_ninja(request, ninja_id, allow_self=True)

    page = Paginator(_badges_queryset(child), BADGES_PAGE_SIZE).get_page(request.GET.get("page"))
    next_page_url = None
    if page.has_next():
        next_page_url = f"{reverse('ninja_badges', kwargs={'ninja_id': child.id})}?page={page.next_page_number()}"

    return render(
        request,
        "accounts/partials/_badges_page.html",
        {
            "badges": page.object_list,
            "badges_next_page_url": next_page_url,
        },
    )
