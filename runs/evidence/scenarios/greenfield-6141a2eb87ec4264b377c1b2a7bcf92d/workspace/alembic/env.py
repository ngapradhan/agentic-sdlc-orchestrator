from sqlalchemy import engine_from_config, pool

from alembic import context
from shortener.models import Base

config = context.config
engine = engine_from_config(
    config.get_section(config.config_ini_section) or {},
    prefix="sqlalchemy.",
    poolclass=pool.NullPool,
)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
