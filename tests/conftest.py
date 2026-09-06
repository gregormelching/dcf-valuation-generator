import sys 
from pathlib import Path

path = Path(__file__).resolve().parent.parent / "logic"
sys.path.insert(0, str(path))

import pytest
import database

FIXTURE_DB = Path(__file__).resolve().parent / "fixtures" / "values.db"

if not FIXTURE_DB.exists():
    pytest.exit(f"Fixture database missing at {FIXTURE_DB}. Run tests/make_fixture.py first.")

@pytest.fixture(autouse = True, scope = "session")
def fixture_db():
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(database, "database", FIXTURE_DB)
        yield

