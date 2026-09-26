from django import template

from privacy.retention import champions_needing_attention

register = template.Library()


@register.simple_tag
def retention_attention_count():
    """For the organisation dashboard's sidebar: champions who can't be
    cleaned until their role moves (privacy.retention)."""
    return len(champions_needing_attention())
