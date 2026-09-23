from django.conf import settings
from django.core.files.storage import FileSystemStorage

# No base_url: this storage's files aren't served by any url() pattern, so
# nothing can build a direct link to them. They're only ever read from disk
# by the permission-gated view in applications.views.
private_storage = FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT, base_url=None)
