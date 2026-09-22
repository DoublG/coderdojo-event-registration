import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "coderdojo-event-registration/1.0 (erik@woidt.be)"


def geocode(address, session=None):
    """Look up (lat, lon) for a free-text address/postcode/city via
    Nominatim, restricted to Belgium. Returns None if nothing matches.
    Raises requests.RequestException on a network/HTTP failure.
    """
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
        return None
    return float(results[0]["lat"]), float(results[0]["lon"])
