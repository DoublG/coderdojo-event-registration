"""The segment builder: groups about accounts or about the same child, all/any,
nested groups, and rules added through fields that fit the attribute (htmx),
each shown as a sentence; live count and sample."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from accounts.organisation import Area, require_area

from ..forms import SegmentForm
from ..models import (
    Campaign,
    Segment,
    SegmentGroup,
    SegmentRule,
)
from ..segmentation.base import OPERATOR_LABELS
from ..segmentation.registry import get_attribute, get_attributes
from ..segmentation.resolver import SegmentResolver
from .common import AUDIENCE_SAMPLE


@login_required
def segment_list(request):
    require_area(request, Area.COMMUNICATION)
    resolver = SegmentResolver()
    rows = [(s, resolver.resolve(s).count()) for s in Segment.objects.order_by("name")]
    return render(request, "mailing/manage/segment_list.html", {"rows": rows, "active": "segments"})


# --- the segment builder -----------------------------------------------------------


def _tree(segment):
    """The segment's groups as nested dicts for the template: each with its
    rules described in words and its child groups."""
    groups = list(segment.groups.prefetch_related("rules").order_by("id"))
    children = {}
    for group in groups:
        children.setdefault(group.parent_id, []).append(group)

    def node(group):
        rules = []
        for rule in sorted(group.rules.all(), key=lambda r: r.pk):
            try:
                text = get_attribute(rule.attribute).describe(rule.operator, rule.value)
            except (ValueError, KeyError, TypeError):
                text = f"{rule.attribute} {rule.operator} {rule.value} (not understood)"
            rules.append({"rule": rule, "text": text})
        return {"group": group, "rules": rules, "children": [node(child) for child in children.get(group.pk, [])]}

    return [node(root) for root in children.get(None, [])]


def _attributes_for(scope):
    return [a for a in get_attributes() if a.scope == scope and a.in_builder]


@login_required
def segment_create(request):
    require_area(request, Area.COMMUNICATION)
    form = SegmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        segment = form.save()
        messages.success(request, _("Segment created. Now add who's in it."))
        return redirect("manage_segment_detail", segment_id=segment.pk)
    return render(request, "mailing/manage/segment_form.html", {"form": form, "active": "segments"})


@login_required
def segment_detail(request, segment_id):
    require_area(request, Area.COMMUNICATION)
    segment = get_object_or_404(Segment, pk=segment_id)
    form = SegmentForm(request.POST or None, instance=segment)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Segment saved."))
        return redirect("manage_segment_detail", segment_id=segment.pk)
    accounts = SegmentResolver().resolve(segment)
    return render(
        request,
        "mailing/manage/segment_detail.html",
        {
            "segment": segment,
            "form": form,
            "tree": _tree(segment),
            "active": "segments",
            "count": accounts.count(),
            "sample": accounts.order_by("pk")[:AUDIENCE_SAMPLE],
            "user_attributes": _attributes_for("user"),
            "ninja_attributes": _attributes_for("ninja"),
            "scopes": SegmentGroup.Scope.choices,
            "operators": SegmentGroup.Operator.choices,
            "draft_campaigns": segment.campaign_set.filter(status=Campaign.Status.DRAFT),
        },
    )


def _back(segment, message=None, request=None, error=False):
    if message:
        (messages.error if error else messages.success)(request, message)
    return redirect("manage_segment_detail", segment_id=segment.pk)


def _validation_text(error):
    return (
        " ".join(m for messages_ in error.message_dict.values() for m in messages_)
        if hasattr(error, "message_dict")
        else " ".join(error.messages)
    )


@login_required
@require_POST
def segment_add_group(request, segment_id):
    require_area(request, Area.COMMUNICATION)
    segment = get_object_or_404(Segment, pk=segment_id)
    parent = (
        get_object_or_404(SegmentGroup, pk=request.POST["parent"], segment=segment)
        if request.POST.get("parent")
        else None
    )
    group = SegmentGroup(
        segment=segment,
        parent=parent,
        scope=request.POST.get("scope", "user"),
        operator=request.POST.get("operator", SegmentGroup.Operator.AND),
    )
    try:
        group.full_clean()
    except ValidationError as error:
        return _back(segment, _validation_text(error), request, error=True)
    group.save()
    return _back(segment)


@login_required
@require_POST
def segment_update_group(request, segment_id, group_id):
    require_area(request, Area.COMMUNICATION)
    group = get_object_or_404(SegmentGroup, pk=group_id, segment_id=segment_id)
    if request.POST.get("operator") in SegmentGroup.Operator.values:
        group.operator = request.POST["operator"]
        group.save(update_fields=["operator"])
    return _back(group.segment)


@login_required
@require_POST
def segment_delete_group(request, segment_id, group_id):
    require_area(request, Area.COMMUNICATION)
    group = get_object_or_404(SegmentGroup, pk=group_id, segment_id=segment_id)
    segment = group.segment
    group.delete()  # its rules and child groups go with it
    return _back(segment, "Group removed.", request)


@login_required
def segment_rule_fields(request, segment_id, group_id):
    """htmx: the operator and value fields for the attribute just picked."""
    require_area(request, Area.COMMUNICATION)
    group = get_object_or_404(SegmentGroup, pk=group_id, segment_id=segment_id)
    try:
        attribute = get_attribute(request.GET.get("attribute", ""))
    except ValueError:
        attribute = None
    return render(
        request,
        "mailing/manage/_rule_fields.html",
        {
            "group": group,
            "attribute": attribute,
            "operators": [(op, OPERATOR_LABELS.get(op, op)) for op in attribute.operators] if attribute else [],
            "choices": attribute.choices() if attribute else [],
        },
    )


@login_required
@require_POST
def segment_add_rule(request, segment_id, group_id):
    require_area(request, Area.COMMUNICATION)
    group = get_object_or_404(SegmentGroup, pk=group_id, segment_id=segment_id)
    try:
        attribute = get_attribute(request.POST.get("attribute", ""))
    except ValueError:
        return _back(group.segment, "Pick what the rule is about.", request, error=True)
    operator = request.POST.get("operator", attribute.operators[0])
    rule = SegmentRule(
        group=group,
        attribute=attribute.key,
        operator=operator,
        value=attribute.value_from_form(operator, request.POST),
    )
    try:
        rule.full_clean()
    except ValidationError as error:
        return _back(group.segment, _validation_text(error), request, error=True)
    rule.save()
    return _back(group.segment, f"Added: {attribute.describe(operator, rule.value)}.", request)


@login_required
@require_POST
def segment_delete_rule(request, segment_id, rule_id):
    require_area(request, Area.COMMUNICATION)
    rule = get_object_or_404(SegmentRule, pk=rule_id, group__segment_id=segment_id)
    segment = rule.group.segment
    rule.delete()
    return _back(segment, "Rule removed.", request)


@login_required
@require_POST
def segment_delete(request, segment_id):
    require_area(request, Area.COMMUNICATION)
    segment = get_object_or_404(Segment, pk=segment_id)
    segment.delete()  # launched campaigns keep their frozen copy
    messages.success(request, _("Segment “%(segment)s” deleted.") % {"segment": segment.name})
    return redirect("manage_segment_list")
