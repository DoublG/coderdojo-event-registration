from django.shortcuts import get_object_or_404, render

from .models import Pathway


def pathway_detail(request, pathway_id):
    pathway = get_object_or_404(Pathway, id=pathway_id)
    other_pathways = Pathway.objects.exclude(id=pathway_id)
    return render(request, "pathways/pathway_detail.html", {"pathway": pathway, "other_pathways": other_pathways})
