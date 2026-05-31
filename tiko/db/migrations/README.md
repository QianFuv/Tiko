# Database Migrations

This directory contains Alembic migrations for the Tiko persistence schema.

Run migrations with an explicit SQLAlchemy database URL:

```text
uv run alembic -x database_url=sqlite+pysqlite:///tiko.db upgrade head
```
