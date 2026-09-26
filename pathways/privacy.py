"""pathways holds the learning-track catalogue only (DATA_MODEL.md §16, `privacy.registry`)."""

from privacy.registry import register_not_personal

from .models import Pathway, PathwayProject, PathwayStep, Skill

for model in (Pathway, PathwayProject, PathwayStep, Skill):
    register_not_personal(model, "the organisation's learning-track catalogue")
