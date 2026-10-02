"""The organisation's campaign pages (/manage/...): campaigns, segments and
journeys, in the Communication area (accounts.organisation.require_area);
every campaign change goes through campaigns.services. Every view is
importable from here, as urls.py does."""

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
