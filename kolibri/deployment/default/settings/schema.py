"""
A settings file for generating in memory databases for schema reflection
and fixture generation purposes.
"""
from .base import *  # noqa isort:skip @UnusedWildImport

DATABASES["default"] = {  # noqa
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": ":memory:",
    "OPTIONS": {"timeout": 100},
}
