from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template import loader

from .models import Pathway


def pathway_detail(request, pathway_id):
    pathway = get_object_or_404(Pathway, id=pathway_id)
    other_pathways = Pathway.objects.exclude(id=pathway_id)
    template = loader.get_template("pathways/pathway_detail.html")
    return HttpResponse(template.render({"pathway": pathway, "other_pathways": other_pathways}, request))
