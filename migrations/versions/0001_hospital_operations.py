"""Add hospital operations without changing or deleting legacy records."""
from alembic import op
from app.db.database import Base
from app.db import models

revision = "0001_operations"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Initial additive baseline supports an existing unversioned prototype DB.
    Base.metadata.create_all(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError("No destructive downgrade. Restore a database backup instead.")
