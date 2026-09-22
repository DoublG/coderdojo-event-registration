from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template import loader
from django.utils import timezone

from .models import Guardian, Participant


def login(request):
    template = loader.get_template("accounts/login.html")
    return HttpResponse(template.render({}, request))


def register(request):
    template = loader.get_template("accounts/register.html")
    return HttpResponse(template.render({}, request))


def register_guardian(request):
    template = loader.get_template("accounts/register_guardian.html")
    return HttpResponse(template.render({}, request))


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
    template = loader.get_template("accounts/guardian_detail.html")
    return HttpResponse(template.render({"guardian": guardian, "children": children}, request))


def child_detail(request, guardian_id, child_id):
    child = get_object_or_404(Participant, id=child_id, guardian_id=guardian_id)
    now = timezone.now()
    history = (
        child.registration_set.filter(event__start_time__lt=now)
        .select_related("event", "event__dojo", "event__mentor")
        .order_by("-event__start_time")
    )
    template = loader.get_template("accounts/child_detail.html")
    return HttpResponse(template.render({"child": child, "history": history}, request))
