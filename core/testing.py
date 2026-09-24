import tempfile
from pathlib import Path


class TempMediaMixin:
    """Stores any file a test saves in a throwaway MEDIA_ROOT instead of the
    real media/ directory."""

    def setUp(self):
        super().setUp()
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        override = self.settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.media_root = Path(media.name)
