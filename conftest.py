"""
Test fixtures. Every test runs against a throwaway SQLite database with
the real migrations applied — no Postgres, no network.

This file is at the repo root so pytest puts the root on sys.path (so
`import db`, `import app` work) and so the env below is set before db.py /
app.py are imported anywhere.
"""

import os
import tempfile

import pytest

_TMP = tempfile.mkdtemp(prefix="muhurata-test-")
os.environ["SQLITE_PATH"] = os.path.join(_TMP, "test.db")
os.environ.pop("DATABASE_URL", None)   # force the SQLite backend
os.environ.pop("DIRECT_URL", None)
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-not-real-000000000000000")
os.environ.setdefault("ADMIN_EMAILS", "admin@example.com")

import migrate  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _apply_migrations():
    assert migrate.main() == 0
    yield


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    import app as appmod

    with TestClient(appmod.app) as c:
        yield c


@pytest.fixture()
def sample_reading_body():
    return {
        "name": "Test Person",
        "dob": "1994-08-14",
        "tob": "07:42",
        "place": "Mumbai",
        "phone": "919876543210",
        "whatsappOptIn": True,
    }
