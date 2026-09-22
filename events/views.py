from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template import loader
from django.utils import timezone

from dojos.models import Dojo

from .models import Event


def event_list(request):
    events = Event.objects.filter(start_time__gte=timezone.now()).select_related("dojo").order_by("start_time")
    dojo_choices = Dojo.objects.filter(event__in=events).distinct().order_by("name")
    template = loader.get_template("events/event_list.html")
    return HttpResponse(template.render({"events": events, "dojo_choices": dojo_choices}, request))


def event_detail(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    template = loader.get_template("events/event_detail.html")
    return HttpResponse(template.render({"event": event}, request))


def event_signup(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    template = loader.get_template("events/event_signup.html")
    return HttpResponse(template.render({"event": event, "full": event.places_left <= 0}, request))
