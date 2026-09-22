from datetime import timedelta

from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from dojos.models import Dojo

from .forms import AGE_RANGES, EventSearchForm
from .models import Event

RESULTS_PER_PAGE = 20


def event_list(request):
    form = EventSearchForm(request.GET)
    now = timezone.now()

    base_events = Event.objects.filter(start_time__gte=now)
    dojo_choices = Dojo.objects.filter(event__in=base_events).distinct().order_by("name")

    events = base_events.select_related("dojo")
    if form.is_valid():
        dojo = form.cleaned_data.get("dojo")
        if dojo:
            events = events.filter(dojo=dojo)

        location = form.cleaned_data.get("location")
        if location:
            events = events.filter(
                Q(dojo__address__icontains=location) | Q(dojo__municipality__name__icontains=location)
            )

        date_bucket = form.cleaned_data.get("date")
        if date_bucket == "week":
            events = events.filter(start_time__lt=now + timedelta(days=7))
        elif date_bucket == "month":
            events = events.filter(start_time__lt=now + timedelta(days=30))

        age_bucket = form.cleaned_data.get("age")
        if age_bucket in AGE_RANGES:
            lo, hi = AGE_RANGES[age_bucket]
            events = events.filter(Q(min_age__isnull=True) | Q(min_age__lte=hi)).filter(
                Q(max_age__isnull=True) | Q(max_age__gte=lo)
            )

    events = events.order_by("start_time")

    paginator = Paginator(events, RESULTS_PER_PAGE)
    page = paginator.get_page(request.GET.get("page"))

    next_page_url = None
    if page.has_next():
        next_params = request.GET.copy()
        next_params["page"] = page.next_page_number()
        next_page_url = f"{request.path}?{next_params.urlencode()}"

    context = {
        "form": form,
        "events": page.object_list,
        "dojo_choices": dojo_choices,
        "total_count": paginator.count,
        "next_page_url": next_page_url,
    }
    # Infinite scroll (htmx "revealed" trigger, see _event_results_page.html):
    # subsequent pages return just the new date-group fragment, not the full page.
    if request.headers.get("HX-Request") == "true":
        return render(request, "events/partials/_event_results_page.html", context)
    return render(request, "events/event_list.html", context)


def event_detail(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    return render(request, "events/event_detail.html", {"event": event})


def event_signup(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    return render(request, "events/event_signup.html", {"event": event, "full": event.places_left <= 0})
