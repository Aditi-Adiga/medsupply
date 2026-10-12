from alembic import context
from app.db.database import engine, Base
from app.db import models

with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
