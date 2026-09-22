from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import LoginForm
from .models import Guardian, Participant


def _post_login_redirect(request, user):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return next_url

    dojo_owner = getattr(user, "dojoowner", None)
    if dojo_owner is not None:
        first_dojo = dojo_owner.dojos.first()
        if first_dojo is not None:
            return reverse("dojo_dashboard", kwargs={"dojo_id": first_dojo.id})

    guardian = getattr(user, "guardian", None)
    if guardian is not None:
        return reverse("guardian_detail", kwargs={"guardian_id": guardian.id})

    child_account = getattr(user, "childaccount", None)
    if child_account is not None and hasattr(child_account, "participant"):
        participant = child_account.participant
        if participant.guardian_id:
            return reverse("child_detail", kwargs={"guardian_id": participant.guardian_id, "child_id": participant.id})

    return reverse("home")


def login(request):
    if request.user.is_authenticated:
        return redirect(_post_login_redirect(request, request.user))

    error = None
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
            )
            if user is not None:
                auth_login(request, user)
                return redirect(_post_login_redirect(request, user))
            error = "That email/password combination doesn't match an account."
    else:
        form = LoginForm()

    return render(request, "accounts/login.html", {"form": form, "error": error})


def logout(request):
    auth_logout(request)
    return redirect("home")


def register(request):
    return render(request, "accounts/register.html")


def register_guardian(request):
    return render(request, "accounts/register_guardian.html")


def guardian_detail(request, guardian_id):
    guardian = get_object_or_404(Guardian, id=guardian_id)
    now = timezone.now()
    children = []
    for child in guardian.children.all():
        next_registration = (
            child.registration_set.filter(waiting_list=False, event__start_time__gte=now)
            .select_related("event")
            .order_by("event__start_time")
            .first()
        )
        children.append({"child": child, "next_registration": next_registration})
    return render(request, "accounts/guardian_detail.html", {"guardian": guardian, "children": children})


def child_detail(request, guardian_id, child_id):
    child = get_object_or_404(Participant, id=child_id, guardian_id=guardian_id)
    now = timezone.now()
    history = (
        child.registration_set.filter(event__start_time__lt=now)
        .select_related("event", "event__dojo", "event__mentor")
        .order_by("-event__start_time")
    )
    return render(request, "accounts/child_detail.html", {"child": child, "history": history})
