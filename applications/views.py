from django.http import HttpResponse
from django.template import loader

from dojos.models import Dojo


def register_dojo(request):
    template = loader.get_template("applications/register_dojo.html")
    return HttpResponse(template.render({}, request))


def register_helper(request):
    dojo_choices = Dojo.objects.order_by("name")
    template = loader.get_template("applications/register_helper.html")
    return HttpResponse(template.render({"dojo_choices": dojo_choices}, request))
