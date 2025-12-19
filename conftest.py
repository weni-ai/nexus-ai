def _disable_migrations(settings):
    try:
        settings.MIGRATION_MODULES = {app.split(".")[-1]: None for app in settings.INSTALLED_APPS}
    except Exception:
        pass


def _patch_charfield(models):
    original_db_type = models.CharField.db_type

    def patched_db_type(self, connection):
        if connection.vendor == "sqlite" and getattr(self, "max_length", None) is None:
            return "text"
        return original_db_type(self, connection)

    models.CharField.db_type = patched_db_type


def _patch_arrayfield(ArrayField):
    import json

    from django.db import models as _models

    original_array_db_type = ArrayField.db_type

    def patched_array_db_type(self, connection):
        if connection.vendor == "sqlite":
            return "text"
        return original_array_db_type(self, connection)

    original_get_prep_value = ArrayField.get_prep_value

    def patched_get_prep_value(self, value):
        from django.db import connection as conn

        if conn.vendor == "sqlite":
            if value is None:
                return None
            return json.dumps(value)
        return original_get_prep_value(self, value)

    original_get_db_prep_value = getattr(ArrayField, "get_db_prep_value", None)

    def patched_get_db_prep_value(self, value, connection, prepared=False):
        if connection.vendor == "sqlite":
            if value is None:
                return None
            try:
                # If value is already a JSON string, keep it; else serialize once
                if isinstance(value, str):
                    json.loads(value)
                    return value
            except Exception:
                pass
            return json.dumps(value)
        if original_get_db_prep_value:
            return original_get_db_prep_value(self, value, connection, prepared)
        return value

    original_from_db_value = getattr(ArrayField, "from_db_value", None)

    def patched_from_db_value(self, value, expression, connection):
        if connection.vendor == "sqlite":
            if value is None:
                return None
            try:
                return json.loads(value)
            except Exception:
                return value
        if original_from_db_value:
            return original_from_db_value(self, value, expression, connection)
        return value

    ArrayField.db_type = patched_array_db_type
    ArrayField.get_prep_value = patched_get_prep_value
    ArrayField.get_db_prep_value = patched_get_db_prep_value
    ArrayField.from_db_value = patched_from_db_value

    original_get_placeholder = getattr(ArrayField, "get_placeholder", None)

    def patched_get_placeholder(self, value, compiler, connection):
        if connection.vendor == "sqlite":
            return "%s"
        if original_get_placeholder:
            return original_get_placeholder(self, value, compiler, connection)
        return _models.Field.get_placeholder(self, value, compiler, connection)

    ArrayField.get_placeholder = patched_get_placeholder


def _patch_queryset_distinct():
    from django.db.models.query import QuerySet as _QuerySet

    _original_qs_distinct = _QuerySet.distinct

    def _patched_qs_distinct(self, *fields):
        from django.db import connection as _conn

        if _conn.vendor == "sqlite" and fields:
            return _original_qs_distinct(self)
        return _original_qs_distinct(self, *fields)

    _QuerySet.distinct = _patched_qs_distinct


def pytest_configure():
    try:
        import redis
        from django.conf import settings
        from django.contrib.postgres.fields import ArrayField
        from django.db import models

        _disable_migrations(settings)
        _patch_charfield(models)
        _patch_arrayfield(ArrayField)
        _patch_queryset_distinct()

        # Disable ElasticAPM during tests to prevent connection leaks
        try:
            settings.ELASTIC_APM = {
                "ENABLED": False,
                "DISABLE_SEND": True,
            }
        except Exception:
            pass

        # Use local memory cache in tests to avoid external Redis
        try:
            settings.CACHES = {
                "default": {
                    "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                    "LOCATION": "unique-snowflake",
                }
            }
        except Exception:
            pass

        # Run Celery tasks eagerly without broker
        try:
            settings.CELERY_TASK_ALWAYS_EAGER = True
            settings.CELERY_TASK_EAGER_PROPAGATES = True
            settings.CELERY_BROKER_URL = "memory://"
            settings.CELERY_RESULT_BACKEND = "cache+memory://"
        except Exception:
            pass

        # Patch redis client to an in-memory stub for tests
        class _FakeRedis:
            def __init__(self):
                self._store = {}

            def set(self, key, value):
                self._store[key] = value.encode("utf-8") if isinstance(value, str) else value

            def setex(self, key, ttl_seconds, value):
                self.set(key, value)

            def get(self, key):
                return self._store.get(key)

            def delete(self, *keys):
                for key in keys:
                    self._store.pop(key, None)

        def _fake_from_url(url):
            return _FakeRedis()

        try:
            redis.Redis.from_url = _fake_from_url  # type: ignore[attr-defined]
            redis.from_url = _fake_from_url  # type: ignore[attr-defined]
            try:
                _FakeRedis.from_url = staticmethod(_fake_from_url)  # type: ignore[attr-defined]
            except Exception:
                pass
        except Exception:
            pass
    except Exception:
        pass


def pytest_unconfigure():
    """Close all database connections after tests to allow test database cleanup."""
    try:
        from django.db import connections

        # Close all database connections
        for conn in connections.all():
            conn.close()
    except Exception:
        pass
