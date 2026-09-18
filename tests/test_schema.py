from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.db.base import Base
from app.db.session import engine


def test_migrations_match_models():
    """Fails if a model changes without a migration (e.g. a column that only exists in Python)."""
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == []
