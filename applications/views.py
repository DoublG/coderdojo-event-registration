from django.shortcuts import render

from dojos.models import Dojo


def register_dojo(request):
    return render(request, "applications/register_dojo.html")


def register_helper(request):
    dojo_choices = Dojo.objects.order_by("name")
    return render(request, "applications/register_helper.html", {"dojo_choices": dojo_choices})
