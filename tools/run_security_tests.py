"""Run Django tests with synthetic uploads isolated from users' files."""
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()
from django.conf import settings
from django.core.management import execute_from_command_line
from django.test import override_settings

if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3":
    raise SystemExit("Security validation requires local SQLite; external databases are refused.")
with TemporaryDirectory(prefix="boutique-test-media-") as media, TemporaryDirectory(prefix="boutique-test-private-") as private:
    with override_settings(MEDIA_ROOT=media, PRIVATE_EXPENSE_ROOT=Path(private)):
        execute_from_command_line(["manage.py", "test", "--noinput", *sys.argv[1:]])
