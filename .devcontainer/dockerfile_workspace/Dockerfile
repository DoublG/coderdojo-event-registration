# Debian 13 (trixie): security support to June 2030. Changing this version? Update its row in
# MAINTENANCE.md ("Development") in the same change.
# Pinned by digest (the multi-platform index): the tag moves with every rebuild
# upstream, the digest can't. Dependabot updates the digest with the tag.
FROM python:3.14-trixie@sha256:446efb4225200a0a196707aa7953898b37962fd3b8859a636035de3af657081e

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

# requirements-dev.txt = the production runtime + dev tools and the data-loading
# libraries (geopandas etc.), compiled with hashes from requirements-dev.in.
COPY requirements-dev.txt /tmp/
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements-dev.txt
