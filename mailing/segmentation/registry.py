from .attributes.event import EventAttribute
from .attributes.registration import (
    RegistrationStatusAttribute
)


SEGMENT_ATTRIBUTES = {
    "event": EventAttribute,
    "registration_status": RegistrationStatusAttribute,
}


def get_attribute(key: str):
    try:
        attribute_class = SEGMENT_ATTRIBUTES[key]
    except KeyError:
        raise ValueError(
            f"Unknown segment attribute: {key}"
        )

    return attribute_class()


def get_attributes():
    return [
        attribute_class()
        for attribute_class in SEGMENT_ATTRIBUTES.values()
    ]
