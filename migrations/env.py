from logging.config import fileConfig

from alembic import context

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.db import Base, engine

if context.config.config_file_name:
    fileConfig(context.config.config_file_name)

with engine.connect() as connection:
    # render_as_batch: SQLite can't ALTER most things, so Alembic rebuilds tables.
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
