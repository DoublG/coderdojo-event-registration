from .attributes.account import AccountTypeAttribute, HasChildrenAttribute
from .attributes.activity import ActiveTeamMemberAttribute, AttendedWithinDaysAttribute
from .attributes.engagement import (
    AttendanceRateAttribute,
    DaysSinceLastVisitAttribute,
    EngagementStageAttribute,
    HasUpcomingAttribute,
    MainDojoStatusAttribute,
    MissedInARowAttribute,
    NoShowsAttribute,
    SessionsAttendedAttribute,
    StageAtDojoAttribute,
)
from .attributes.event import EventAttribute
from .attributes.locality import LanguageAttribute, NearDojoAttribute, ProvinceAttribute
from .attributes.ninja import NinjaGenderAttribute
from .attributes.profile import (
    AccountRoleAttribute,
    CancellationsAttribute,
    CurrentBeltAttribute,
    HasBadgeAttribute,
    HomeDojoAttribute,
    JoinedAttribute,
    NinjaAgeAttribute,
    PathwayAttribute,
    WaitlistedForEventAttribute,
)
from .attributes.registration import AttendedEventAttribute

SEGMENT_ATTRIBUTES = {
    attribute.key: attribute
    for attribute in [
        AccountRoleAttribute,
        AccountTypeAttribute,
        JoinedAttribute,
        HasChildrenAttribute,
        ActiveTeamMemberAttribute,
        LanguageAttribute,
        ProvinceAttribute,
        NearDojoAttribute,
        NinjaGenderAttribute,
        NinjaAgeAttribute,
        HomeDojoAttribute,
        CurrentBeltAttribute,
        HasBadgeAttribute,
        PathwayAttribute,
        WaitlistedForEventAttribute,
        CancellationsAttribute,
        AttendedWithinDaysAttribute,
        EngagementStageAttribute,
        StageAtDojoAttribute,
        AttendanceRateAttribute,
        SessionsAttendedAttribute,
        MissedInARowAttribute,
        DaysSinceLastVisitAttribute,
        NoShowsAttribute,
        HasUpcomingAttribute,
        MainDojoStatusAttribute,
        EventAttribute,
        AttendedEventAttribute,
    ]
}


def get_attribute(key: str):
    try:
        attribute_class = SEGMENT_ATTRIBUTES[key]
    except KeyError:
        raise ValueError(
            f"Unknown segment attribute: {key}"
        ) from None

    return attribute_class()


def get_attributes():
    return [
        attribute_class()
        for attribute_class in SEGMENT_ATTRIBUTES.values()
    ]
