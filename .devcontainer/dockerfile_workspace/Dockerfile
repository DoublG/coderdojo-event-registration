FROM python:3.14-bookworm

# git/curl/ca-certificates: general tooling (ca-certificates also needed so
# start.sh can add our local dev CA to the trust store).
# build-essential/pkg-config/default-libmysqlclient-dev: mysqlclient builds
# a C extension against libmysqlclient at pip-install time.
# gdal-bin/libgdal-dev/libgeos-dev/libproj-dev: django.contrib.gis (see
# geo/functions.py) and the geopandas stack load these as shared libs via
# ctypes at runtime, not via pip.
# gettext: Django translation catalogs (website/settings.py LANGUAGES).
RUN apt-get update && apt-get install -y \
    git \
    curl \
    ca-certificates \
    build-essential \
    pkg-config \
    default-libmysqlclient-dev \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    gettext \
    && rm -rf /var/lib/apt/lists/*

# requirements-dev.txt = requirements.txt (production runtime) + dev tools and
# the data-loading libraries (geopandas etc.) — the container needs both.
COPY requirements.txt requirements-dev.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements-dev.txt
