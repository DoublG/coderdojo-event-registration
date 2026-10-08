"""The organisation's mail dashboard pages that are the engine's own (/manage/...):
mail templates, the mail queue and the mail log, in the Communication area
(accounts.organisation.require_area, DATA_MODEL.md §23). The campaign pages
are campaigns.manage. Every view is importable from here, as urls.py does."""

from .queue import (  # noqa: F401
    MAIL_LOG_PAGE_SIZE,
    MAIL_QUEUE_LIMIT,
    MAIL_QUEUE_RECENT_DAYS,
    mail_block,
    mail_block_domain,
    mail_log,
    mail_queue,
    mail_retry,
    mail_retry_failed,
    mail_unblock,
    mail_unblock_domain,
)
from .templates import (  # noqa: F401
    _sample_context,
    template_create,
    template_delete,
    template_edit,
    template_list,
)
