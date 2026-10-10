"""Turning a typed address into coordinates (the dojo finder, a dojo's own
address, `import_dojos`).

Nominatim (OpenStreetMap's public geocoder) allows at most one request a
second for the whole site, and asks every user to cache what it can
(https://operations.osmfoundation.org/policies/nominatim/). So, in order:

1. **The cache** (Redis), by the normalised text: "9000, Gent " and
   "9000 gent" are one entry. A match is kept for FOUND_CACHE_TIMEOUT (an
   address doesn't move), a no-match for NOT_FOUND_CACHE_TIMEOUT. The key is
   a hash, so what someone typed (it can be a home address) is never stored
   as text, only the coordinates it gave.
2. **Our own municipalities** (`geo.Municipality`): a Belgian postcode, a
   municipality's name, or both, are answered from the database, the way
   most people search the dojo finder. A name found in places far apart is
   left to Nominatim.
3. **Nominatim**, one request a second for every process together: a slot
   in Redis (`SLOT_KEY`) is taken before each call, and a web request waits
   at most WEB_WAIT_SECONDS for it. A 429, 503 or 403 from Nominatim stops
   every call for a while (`BACKOFF_KEY`). Without Redis there's no call at
   all, rather than calls nobody counts. Not getting a slot raises
   `GeocodingUnavailable`, a `requests.RequestException`, which every caller
   already treats as a failed lookup (and which is never cached).
"""

import hashlib
import logging
import re
import time
import unicodedata

import requests
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.core.cache import cache
from django_redis import get_redis_connection

from monitoring import recorder

from .models import AdministrativeBoundary, Municipality

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "coderdojo-event-registration/1.0 (erik@woidt.be)"

FOUND_CACHE_TIMEOUT = 60 * 60 * 24 * 90  # 90 days: an address doesn't move
NOT_FOUND_CACHE_TIMEOUT = 60 * 60 * 24  # a day: a typo stays a typo
CACHE_KEY = "geo:geocode:{digest}"

# Nominatim's limit is one request a second; a little margin on top.
MIN_INTERVAL_MS = 1100
SLOT_KEY = "geo:nominatim:slot"
BACKOFF_KEY = "geo:nominatim:backoff"
BACKOFF_SECONDS = {429: 60, 503: 60, 403: 3600}  # 403: blocked, a usage-policy problem to look at
WEB_WAIT_SECONDS = 2  # how long a page waits for a slot before giving up

# Municipalities sharing a name further apart than this (in degrees, about
# 15 km) are different places: not answered locally.
LOCAL_SPREAD_DEGREES = 0.15
COUNTRY_SUFFIX = re.compile(r"[\s,]*\b(belgium|belgie|belgië|belgique|belgien|be)$")

_NOT_FOUND = object()  # cache.get(..., default) can't tell "miss" from "cached None"


class GeocodingUnavailable(requests.RequestException):
    """No request to Nominatim now: no slot within the wait, a back-off after
    an error from Nominatim, or no Redis to count requests with."""


def normalise(address: str) -> str:
    """The text that identifies a search: case, accents' composition,
    commas, spacing and a trailing country name don't matter."""
    text = unicodedata.normalize("NFKC", address).casefold()
    text = re.sub(r"[\s,;]+", " ", text).strip()
    return COUNTRY_SUFFIX.sub("", text).strip()


def _cache_key(normalised: str) -> str:
    return CACHE_KEY.format(digest=hashlib.sha256(normalised.encode()).hexdigest()[:32])


def local_lookup(normalised: str) -> tuple[float, float] | None:
    """(lat, lon) from geo.Municipality for a postcode, a municipality's
    name, or both ("9000", "gent", "9000 gent", "gent 9000"), else None."""
    match = re.fullmatch(r"(\d{4})(?: (.+))?|(.+) (\d{4})", normalised)
    if match:
        postal_code = match.group(1) or match.group(4)
        name = match.group(2) or match.group(3)
        rows = list(Municipality.objects.filter(postal_code=postal_code, name__iexact=name)) if name else []
        if not rows:
            rows = list(Municipality.objects.filter(postal_code=postal_code))
    elif normalised and not any(char.isdigit() for char in normalised):
        rows = list(Municipality.objects.filter(name__iexact=normalised))
    else:
        rows = []
    if not rows:
        return None
    lons, lats = [row.center.x for row in rows], [row.center.y for row in rows]
    if max(lons) - min(lons) > LOCAL_SPREAD_DEGREES or max(lats) - min(lats) > LOCAL_SPREAD_DEGREES:
        return None
    return sum(lats) / len(lats), sum(lons) / len(lons)


def _take_slot(wait: float | None) -> None:
    """Wait for the site's one Nominatim request a second (at most `wait`
    seconds; None: as long as it takes)."""
    try:
        redis = get_redis_connection("default")
        deadline = None if wait is None else time.monotonic() + wait
        while True:
            backoff = redis.pttl(BACKOFF_KEY)
            if backoff > 0:
                if deadline is not None and time.monotonic() + backoff / 1000 > deadline:
                    raise GeocodingUnavailable("Nominatim asked us to slow down; trying again later.")
                time.sleep(backoff / 1000)
                continue
            if redis.set(SLOT_KEY, 1, nx=True, px=MIN_INTERVAL_MS):
                return
            pause = max(redis.pttl(SLOT_KEY), 20) / 1000
            if deadline is not None and time.monotonic() + pause > deadline:
                raise GeocodingUnavailable("Nominatim is busy with our other requests.")
            time.sleep(pause)
    except GeocodingUnavailable:
        raise
    except Exception as error:  # no Redis: no way to keep to the limit
        logger.warning("Geocoding: no request to Nominatim without Redis (%s)", error)
        raise GeocodingUnavailable("No Redis to keep to Nominatim's limit.") from error


def _back_off(response: requests.Response) -> None:
    seconds = BACKOFF_SECONDS.get(response.status_code)
    if seconds is None:
        return
    retry_after = response.headers.get("Retry-After", "")
    if retry_after.isdigit():
        seconds = max(seconds, int(retry_after))
    logger.warning("Geocoding: Nominatim answered %s, no requests for %s s", response.status_code, seconds)
    try:
        get_redis_connection("default").set(BACKOFF_KEY, 1, ex=seconds)
    except Exception:
        logger.debug("Couldn't store the Nominatim back-off", exc_info=True)


def _nominatim(address: str, session: requests.Session | None) -> tuple[float, float] | None:
    query = address if "belgium" in address.lower() else f"{address}, Belgium"
    params: dict[str, str | int] = {"q": query, "format": "json", "limit": 1, "countrycodes": "be"}
    response = (session or requests).get(
        NOMINATIM_URL,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    if response.status_code in BACKOFF_SECONDS:
        _back_off(response)
    response.raise_for_status()
    results = response.json()
    return (float(results[0]["lat"]), float(results[0]["lon"])) if results else None


def geocode(
    address: str, session: requests.Session | None = None, wait: float | None = WEB_WAIT_SECONDS
) -> tuple[float, float] | None:
    """(lat, lon) for a free-text Belgian address, postcode or town, or None
    when nothing matches. Raises requests.RequestException when it couldn't
    find out (a network or HTTP error, or GeocodingUnavailable): never
    cached, so the next try asks again. `wait`: how long to wait for a
    Nominatim slot (None for a command that may wait, like import_dojos)."""
    normalised = normalise(address)
    if not normalised:
        return None
    key = _cache_key(normalised)
    cached = cache.get(key, _NOT_FOUND)
    recorder.note_cache("geo:geocode", hit=cached is not _NOT_FOUND)
    if cached is not _NOT_FOUND:
        return cached

    coords = local_lookup(normalised)
    recorder.note_cache("geo:local-lookup", hit=coords is not None)  # a miss is a Nominatim request
    if coords is None:
        _take_slot(wait)
        # Someone else may have looked it up while this one waited.
        cached = cache.get(key, _NOT_FOUND)
        if cached is not _NOT_FOUND:
            return cached
        coords = _nominatim(address, session)
    cache.set(key, coords, FOUND_CACHE_TIMEOUT if coords else NOT_FOUND_CACHE_TIMEOUT)
    return coords


def find_province(location: Point) -> AdministrativeBoundary | None:
    """The Belgian province (AdministrativeBoundary, kind=PROVINCE) a point
    falls inside — used to keep Dojo.province in sync with Dojo.location
    (see dojos.views.dojo_manage and the one-time backfill this was
    factored out of, dojos.management.commands.map_dojo_provinces)."""
    province = AdministrativeBoundary.objects.filter(
        kind=AdministrativeBoundary.PROVINCE, boundary__contains=location
    ).first()
    if province:
        return province
    # Falls back to nearest province for points just outside every polygon
    # (e.g. a coastal/border dojo, or an edge simplified away by
    # import_boundaries' tolerance).
    return (
        AdministrativeBoundary.objects.filter(kind=AdministrativeBoundary.PROVINCE)
        .annotate(distance=Distance("boundary", location))
        .order_by("distance")
        .first()
    )
