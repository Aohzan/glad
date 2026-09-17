"""Container health check: GET /health with the configured public hostname."""

import os
import sys
import urllib.request
from urllib.parse import urlparse

# Django validates the Host header against ALLOWED_HOSTS, which defaults to the
# APP_URL hostname, so present that hostname rather than 127.0.0.1.
HOST = urlparse(os.environ.get("APP_URL", "")).hostname or "localhost"
URL = "http://127.0.0.1:8000/health"

try:
    request = urllib.request.Request(URL, headers={"Host": HOST})
    with urllib.request.urlopen(request, timeout=4) as response:
        sys.exit(0 if response.status == 200 else 1)
except Exception as exc:
    print(f"health check failed: {exc}", file=sys.stderr)
    sys.exit(1)
