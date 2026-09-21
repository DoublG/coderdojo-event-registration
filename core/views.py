from django.http import HttpResponse
from django.template import loader


def home(request):
    template = loader.get_template("core/home.html")
    context = {}
    return HttpResponse(template.render(context, request))

def events(request):
    template = loader.get_template("core/events.html")
    context = {}
    return HttpResponse(template.render(context, request))

def dojo(request, dojo_id):
    template = loader.get_template("core/dojo.html")
    context = {"id": dojo_id}
    return HttpResponse(template.render(context, request))

def dojo_list(request):
    template = loader.get_template("core/dojo-finder.html")
    context = {}
    return HttpResponse(template.render(context, request))

def event(request, event_id=None, dojo_id=None):
    template = loader.get_template("core/event-detail.html")
    context = {"id": event_id}
    return HttpResponse(template.render(context, request))

def guardian(request, guardian_id):
    template = loader.get_template("core/guardian-dashboard.html")
    context = {"id": guardian_id}
    return HttpResponse(template.render(context, request))

def child(request, guardian_id, child_id):
    template = loader.get_template("core/child-profile.html")
    context = {"id": child_id}
    return HttpResponse(template.render(context, request))

def profile(request, profile_id):
    template = loader.get_template("core/board-profile.html")
    context = {"id": profile_id}
    return HttpResponse(template.render(context, request))

def team(request, dojo_id):
    template = loader.get_template("core/mentor-detail.html")
    context = {"id": dojo_id}
    return HttpResponse(template.render(context, request))

def register(request):
    template = loader.get_template("core/register-choice.html")
    context = {}
    return HttpResponse(template.render(context, request))

def register_helper(request):
    template = loader.get_template("core/register-helper.html")
    context = {}
    return HttpResponse(template.render(context, request))

def register_dojo(request):
    template = loader.get_template("core/register-dojo.html")
    context = {}
    return HttpResponse(template.render(context, request))

def register_guardian(request):
    template = loader.get_template("core/register.html")
    context = {}
    return HttpResponse(template.render(context, request))

def register(request):
    template = loader.get_template("core/register-choice.html")
    context = {}
    return HttpResponse(template.render(context, request))

def admin(request):
    template = loader.get_template("core/admin-dashboard.html")
    context = {}
    return HttpResponse(template.render(context, request))

def signup_event(request, event_id):
    template = loader.get_template("core/event-signup.html")
    context = {"id": event_id}
    return HttpResponse(template.render(context, request))

def login(request):
    template = loader.get_template("core/login.html")
    context = {}
    return HttpResponse(template.render(context, request))

def pathway(request, pathway_id):
    template = loader.get_template("core/pathway-detail.html")
    context = {"id": pathway_id}
    return HttpResponse(template.render(context, request))