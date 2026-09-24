"""Production entry point for Level27's Python hosting.

Level27 runs the site as `gunicorn -k uvicorn.workers.UvicornWorker main:app`
from ~/app (the command is managed on their side, not in this repo), so this
module only re-exports the project's ASGI application under that name. See
website/asgi.py for the actual routing (HTTP → Django, WebSocket → Channels)
and scripts/deploy.sh for how code gets onto the server.
"""

from website.asgi import application as app  # noqa: F401
