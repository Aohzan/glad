#!/usr/bin/env python3
"""Take the README screenshots from the demo data with headless Chromium.

The demo data of scripts/generate_fixtures.py is loaded in a throwaway SQLite
database (data/glad.db is never touched) and served with the demo user
logged in. Each page is captured in dark theme and French, 1656 px wide and
as high as its content, into docs/images/.

Usage: uv run python scripts/screenshots.py [name ...]

Without name, every page of PAGES is taken. Set CHROMIUM to the browser
binary when it is not found on the PATH. Look at each image before
committing it: a fixed height may need adjusting after a layout change.
"""

import datetime
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageChops

PROJECT_DIR = Path(__file__).resolve().parent.parent
IMAGES_DIR = PROJECT_DIR / "docs" / "images"
WIDTH = 1656
#: Lowest height of a page, so the sidebar is never cut.
MIN_HEIGHT = 900
#: Height of the first capture, cropped afterwards to the page content.
MAX_HEIGHT = 6000
YEAR = datetime.date.today().year

#: (image name, path, fixed height or None for the height of the content)
PAGES = [
    ("dashboard_hero", "/", 927),
    ("dashboard", "/", None),
    ("finance_home", "/finance/", None),
    ("finance_invest", "/finance/investment/1/", None),
    ("finance_batch_update", "/finance/update", None),
    ("property_home", "/property/", None),
    ("property_details", "/property/1/", None),
    (
        "property_accounting",
        f"/property/report/?start_date={YEAR - 1}-01-01&end_date={YEAR - 1}-12-31",
        None,
    ),
    ("property_lmnp", "/property/lmnp_accounting/", None),
    ("scpi", "/property/scpi/", None),
    # Down to the end of the sankey diagram.
    ("budget", f"/budget/{YEAR}/", 1248),
]

SETTINGS = """
from glad.settings import *  # noqa: F403

DATABASES = {{"default": {{"ENGINE": "django.db.backends.sqlite3", "NAME": {db!r}}}}}
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
LANGUAGE_CODE = "fr"
MIDDLEWARE = list(MIDDLEWARE)  # noqa: F405
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware") + 1,
    "screenshot_login.AutoLogin",
)
"""

AUTO_LOGIN = """
from django.contrib.auth import get_user_model, login


class AutoLogin:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            user = get_user_model().objects.filter(is_superuser=True).first()
            if user is not None:
                login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return self.get_response(request)
"""

#: The demo user is the household member "mister", and the recurring entries
#: are checked so the dashboard shows no reminder banner.
PREPARE = """
import datetime
from django.contrib.auth import get_user_model
from property.services.checks import check_all_up_to

get_user_model().objects.filter(username="mister").update(is_superuser=True, is_staff=True)
check_all_up_to(datetime.date.today())
"""


def chromium() -> str:
    """Path of the Chromium or Chrome binary."""
    for name in (
        os.environ.get("CHROMIUM"),
        "chromium",
        "chromium-browser",
        "google-chrome",
    ):
        if name and shutil.which(name):
            return name
    sys.exit("Chromium not found: set CHROMIUM to the browser binary.")


def free_port() -> int:
    """A TCP port nobody listens to."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def manage(env: dict, *args: str) -> None:
    """Run a manage.py command on the demo database."""
    subprocess.run(
        [sys.executable, "manage.py", *args],
        cwd=PROJECT_DIR,
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
    )


def demo_environment(workdir: Path) -> dict:
    """Environment of the commands using the throwaway database."""
    (workdir / "screenshot_settings.py").write_text(
        SETTINGS.format(db=str(workdir / "demo.db"))
    )
    (workdir / "screenshot_login.py").write_text(AUTO_LOGIN)
    env = dict(os.environ)
    env.setdefault("ENV_FILE", str(PROJECT_DIR / ".env.dev"))
    env["PYTHONPATH"] = os.pathsep.join([str(workdir), str(PROJECT_DIR)])
    env["DJANGO_SETTINGS_MODULE"] = "screenshot_settings"
    return env


def load_demo(env: dict) -> None:
    """Create the throwaway database and load the demo data."""
    subprocess.run(
        [sys.executable, "scripts/generate_fixtures.py"],
        cwd=PROJECT_DIR,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    manage(env, "migrate")
    fixtures = sorted(PROJECT_DIR.glob("finance/fixtures/*.yaml")) + sorted(
        PROJECT_DIR.glob("tests/fixtures/*.yaml")
    )
    manage(env, "loaddata", *(str(path) for path in fixtures))
    manage(env, "shell", "-c", PREPARE)


def wait_for(url: str, timeout: float = 60) -> None:
    """Wait until *url* answers."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except OSError:
            time.sleep(0.5)
    sys.exit(f"The demo server did not start: {url}")


def shoot(browser: str, url: str, height: int, target: Path) -> None:
    """Capture *url* in dark theme and French."""
    subprocess.run(
        [
            browser,
            "--headless=new",
            "--hide-scrollbars",
            "--force-dark-mode",
            "--blink-settings=preferredColorScheme=0",
            "--force-prefers-reduced-motion",
            "--lang=fr-FR",
            "--accept-lang=fr-FR",
            "--virtual-time-budget=20000",
            f"--window-size={WIDTH},{height}",
            f"--screenshot={target}",
            url,
        ],
        check=True,
        capture_output=True,
    )


def content_bottom(image: Path) -> int:
    """Last row of the main column that differs from the page background.

    The sidebar (left) and the footer (bottom of the window) are left out.
    """
    img = Image.open(image).convert("RGB")
    width, height = img.size
    main = img.crop((300, 0, width, height - 80))
    background = Image.new("RGB", main.size, img.getpixel((width - 3, height - 120)))
    changed = ImageChops.difference(main, background).point(
        lambda value: 255 if value > 12 else 0
    )
    box = changed.getbbox()
    return box[3] if box else height


def main() -> None:
    """Take the screenshots named on the command line, or all of them."""
    wanted = set(sys.argv[1:])
    unknown = wanted - {name for name, _path, _height in PAGES}
    if unknown:
        sys.exit(f"Unknown screenshots: {', '.join(sorted(unknown))}")
    browser = chromium()
    with tempfile.TemporaryDirectory(prefix="glad-screenshots-") as tmp:
        workdir = Path(tmp)
        env = demo_environment(workdir)
        print("Loading the demo data…")
        load_demo(env)
        port = free_port()
        server = subprocess.Popen(
            [
                sys.executable,
                "manage.py",
                "runserver",
                f"127.0.0.1:{port}",
                "--noreload",
            ],
            cwd=PROJECT_DIR,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            base = f"http://127.0.0.1:{port}"
            wait_for(f"{base}/health")
            for name, path, height in PAGES:
                if wanted and name not in wanted:
                    continue
                target = IMAGES_DIR / f"{name}.png"
                if height is None:
                    shoot(browser, base + path, MAX_HEIGHT, target)
                    height = min(MAX_HEIGHT, content_bottom(target) + 110)
                    height = max(MIN_HEIGHT, height)
                shoot(browser, base + path, height, target)
                print(f"  {target.relative_to(PROJECT_DIR)} ({WIDTH}×{height})")
        finally:
            server.terminate()
            server.wait()


if __name__ == "__main__":
    main()
