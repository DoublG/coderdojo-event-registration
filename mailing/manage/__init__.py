"""The organisation's mail dashboard pages that are the engine's own (/manage/...):
mail templates and the mail queue, in the Communication area
(accounts.organisation.require_area, DATA_MODEL.md §23). The campaign pages
are campaigns.manage. Every view is importable from here, as urls.py does."""

from .queue import (  # noqa: F401
    MAIL_QUEUE_LIMIT,
    MAIL_QUEUE_RECENT_DAYS,
    mail_queue,
)
from .templates import (  # noqa: F401
    _sample_context,
    template_create,
    template_delete,
    template_edit,
    template_list,
)
