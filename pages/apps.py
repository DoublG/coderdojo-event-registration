from django.apps import AppConfig


class PagesConfig(AppConfig):
    """The site as visitors and the organisation meet it, assembled from the
    other apps: the homepage, the Contact and Code of conduct pages,
    /manage/'s landing, the audit log page, the health check, the Django
    admin site and the content seeders' translations. Nothing imports it
    (CODING_STANDARDS.md, "Layers")."""

    name = "pages"
