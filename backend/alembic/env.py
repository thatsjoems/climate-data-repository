from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
import os, sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.core.config import settings
from app.core.database import Base
from app.models import models  # noqa: F401

config = context.config
# A restricted runtime role (docs/DATABASE_OPERATIONS.md) cannot run DDL, so migrations may be given
# their own owner-level URL. Unset or empty = the runtime DATABASE_URL, i.e. unchanged behaviour.
MIGRATION_URL = os.environ.get('MIGRATION_DATABASE_URL') or settings.DATABASE_URL
if MIGRATION_URL:
    config.set_main_option('sqlalchemy.url', MIGRATION_URL.replace('%', '%%'))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(url=MIGRATION_URL, target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix='sqlalchemy.', poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
