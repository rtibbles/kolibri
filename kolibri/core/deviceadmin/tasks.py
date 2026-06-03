import logging

from django import db
from django.apps import apps

from kolibri.core.tasks.decorators import register_task
from kolibri.core.tasks.schedules import Cron
from kolibri.utils.conf import OPTIONS
from kolibri.utils.file_transfer import ChunkedFileDirectoryManager

logger = logging.getLogger(__name__)

# Constant job_id for vacuum task
SCH_VACUUM_JOB_ID = "1"


def _optimize_sqlite_db(database):
    connection = db.connections[database]
    db_name = connection.settings_dict["NAME"]
    try:
        connection.close_if_unusable_or_obsolete()
        connection.close()
        cursor = connection.cursor()
        cursor.execute("vacuum;")
        cursor.execute("PRAGMA optimize;")
        connection.close()
    except Exception as e:
        logger.error(e)
        new_msg = (
            "Vacuum of database {db_name} couldn't be executed. Possible reasons:\n"
            "  * There is an open transaction in the db.\n"
            "  * There are one or more active SQL statements.\n"
            "The full error: {error_msg}"
        ).format(db_name=db_name, error_msg=e)
        logger.error(new_msg)
    else:
        logger.info(f"Sqlite database Vacuum and optimize for {db_name} finished.")


@register_task(job_id=SCH_VACUUM_JOB_ID, schedule=Cron(hour=3))
def perform_vacuum(database=None, full=False):
    connection = db.connections[database or db.DEFAULT_DB_ALIAS]
    if connection.vendor == "sqlite":
        databases = (
            [database] if database is not None else [name for name in db.connections]
        )
        # No db_lock here: SQLite refuses to VACUUM from inside a transaction, and
        # db_lock opens one.
        for db_name in databases:
            _optimize_sqlite_db(db_name)
    elif connection.vendor == "postgresql":
        if full:
            morango_models = ("morango_recordmaxcounterbuffer", "morango_buffer")
        else:
            morango_models = [
                m
                for m in apps.get_models(include_auto_created=True)
                if "morango.models" in str(m)
            ]
        cursor = connection.cursor()
        for m in morango_models:
            if full:
                cursor.execute("vacuum full analyze {};".format(m))
            else:
                cursor.execute("vacuum analyze {};".format(m._meta.db_table))
        connection.close()


# Constant job id for streamed cache cleanup task
STREAMED_CACHE_CLEANUP_JOB_ID = "streamed_cache_cleanup"


@register_task(job_id=STREAMED_CACHE_CLEANUP_JOB_ID, schedule=Cron(minute=0))
def streamed_cache_cleanup():
    manager = ChunkedFileDirectoryManager(OPTIONS["Paths"]["CONTENT_DIR"])
    manager.limit_files(OPTIONS["Cache"]["STREAMED_FILE_CACHE_SIZE"])
