import requests
from django.core.cache import cache

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "coderdojo-event-registration/1.0 (erik@woidt.be)"

# An address's coordinates don't change, so a hit is cached for a long time.
# A miss/no-match gets a much shorter one — worth re-checking sooner, in
# case it was a typo since fixed, or we're getting rate-limited by
# Nominatim's public instance rather than genuinely finding nothing.
FOUND_CACHE_TIMEOUT = 60 * 60 * 24 * 7  # 1 week
NOT_FOUND_CACHE_TIMEOUT = 60 * 10  # 10 minutes

_NOT_FOUND = object()  # cache.get(..., default) can't tell "miss" from "cached None"


def geocode(address, session=None):
    """Look up (lat, lon) for a free-text address/postcode/city via
    Nominatim, restricted to Belgium. Returns None if nothing matches.
    Raises requests.RequestException on a network/HTTP failure.

    Results are cached (by normalized address) — this is a real network
    call against a shared, rate-limited public API (Nominatim's usage
    policy), and repeat searches for the same town/postcode are common
    (it backs both the dojo finder and its homepage widget).
    """
    cache_key = f"geo:geocode:{address.strip().lower()}"
    cached = cache.get(cache_key, _NOT_FOUND)
    if cached is not _NOT_FOUND:
        return cached

    query = address if "belgium" in address.lower() else f"{address}, Belgium"
    http = session or requests
    response = http.get(
        NOMINATIM_URL,
        params={"q": query, "format": "json", "limit": 1, "countrycodes": "be"},
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    response.raise_for_status()
    results = response.json()

    if not results:
        cache.set(cache_key, None, NOT_FOUND_CACHE_TIMEOUT)
        return None

    coords = float(results[0]["lat"]), float(results[0]["lon"])
    cache.set(cache_key, coords, FOUND_CACHE_TIMEOUT)
    return coords
