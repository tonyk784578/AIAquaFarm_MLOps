"""Alembic migration scripts package.

Run migrations with:
    alembic upgrade head          # apply all pending migrations
    alembic revision --autogenerate -m "description"  # create new migration

TODO (Phase 1): Run `alembic init alembic` at backend root,
    then configure alembic/env.py to use app.db.session.Base.
"""
