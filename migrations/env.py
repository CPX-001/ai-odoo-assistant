"""Alembic environment for the separate Assistant PostgreSQL database."""

from alembic import context

from odoo_ai.storage import Base, DatabaseSettings
from odoo_ai.storage.database import create_database_engine

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    settings = DatabaseSettings.from_env()
    context.configure(
        url=settings.url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_database_engine(DatabaseSettings.from_env())
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
