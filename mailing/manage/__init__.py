"""The organisation's management dashboard for mail (/manage/..., shell
core/_manage_base.html), by page: campaigns, segments, journeys, mail
templates and the mail queue. Only the Communication area gets in
(accounts.organisation.require_area, the admin role, DATA_MODEL.md §23); every
campaign change goes through mailing.campaigns. Every view is importable from
here, as urls.py does."""

from .campaigns import (  # noqa: F401
    _campaign_action,
    _dojo_audience,
    _previews,
    campaign_cancel,
    campaign_create,
    campaign_detail,
    campaign_launch,
    campaign_list,
    campaign_test,
)
from .common import (  # noqa: F401
    AUDIENCE_SAMPLE,
)
from .journeys import (  # noqa: F401
    _journey_action,
    journey_activate,
    journey_create,
    journey_detail,
    journey_list,
    journey_pause,
    journey_test,
)
from .queue import (  # noqa: F401
    MAIL_QUEUE_LIMIT,
    MAIL_QUEUE_RECENT_DAYS,
    mail_queue,
)
from .segments import (  # noqa: F401
    _attributes_for,
    _back,
    _tree,
    _validation_text,
    segment_add_group,
    segment_add_rule,
    segment_create,
    segment_delete,
    segment_delete_group,
    segment_delete_rule,
    segment_detail,
    segment_list,
    segment_rule_fields,
    segment_update_group,
)
from .templates import (  # noqa: F401
    _sample_context,
    template_create,
    template_delete,
    template_edit,
    template_list,
)
