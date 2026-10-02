"""The dojos app's pages, by area: the public pages (public), a dojo's settings,
lifecycle and updates (profile), its team (team_pages), its sessions
(event_pages), attendance and awards (attendance) and the notification bell
(bell), with what they share (common). Every view is importable from here, as
urls.py does."""

from .attendance import (  # noqa: F401
    ATTENDANCE_VALUES,
    _attendance_context,
    _award_forms,
    _award_view,
    _awardable_badges,
    _awardable_belts,
    _team_attendance_rows,
    dojo_dashboard,
    dojo_event_attendance,
    dojo_event_attendance_mark,
    dojo_event_attendance_mark_all,
    dojo_event_award_badge,
    dojo_event_award_belt,
    dojo_event_registration_pathways,
    dojo_event_team_attendance_mark,
)
from .bell import (  # noqa: F401
    mark_all_notifications_read,
    open_notification,
)
from .common import (  # noqa: F401
    NOTIFICATION_LIMIT,
    PUBLIC_UPDATES_LIMIT,
    RESULTS_PER_PAGE,
    WIDGET_RESULTS_LIMIT,
    _admin_context,
    _notification_context,
)
from .event_pages import (  # noqa: F401
    _event_promotions_context,
    dojo_event_create,
    dojo_event_detail,
    dojo_event_list,
    dojo_event_set_status,
)
from .profile import (  # noqa: F401
    _geocode_address,
    dojo_create,
    dojo_manage,
    dojo_set_lifecycle,
    dojo_update_delete,
    dojo_updates,
)
from .public import (  # noqa: F401
    _join_state,
    dojo_detail,
    dojo_finder_widget,
    dojo_join_request,
    dojo_list,
    dojo_team,
    team_member_detail,
)
from .team_pages import (  # noqa: F401
    TEAM_ACTIONS,
    _team_accept,
    _team_add_mentor,
    _team_decline,
    _team_leave,
    _team_promote,
    _team_remove,
    _team_transfer,
    _youth_mentor_candidates,
    dojo_members,
    dojo_team_action,
    dojo_team_manage,
)
