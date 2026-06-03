from django import db
from django.test import TransactionTestCase
from mock import patch

from kolibri.core.deviceadmin.tasks import perform_vacuum


def _is_sqlite(alias=None):
    return db.connections[alias or db.DEFAULT_DB_ALIAS].vendor == "sqlite"


class PerformVacuumTestCase(TransactionTestCase):
    """
    TransactionTestCase, not TestCase: TestCase wraps each test in a transaction,
    and SQLite refuses to VACUUM from inside one.
    """

    databases = "__all__"

    def setUp(self):
        if not _is_sqlite():
            self.skipTest("SQLite-specific behaviour")

    def test_vacuum_does_not_swallow_an_error(self):
        # perform_vacuum logs and discards any exception, so a broken vacuum is
        # silent. Assert nothing was logged as an error.
        with patch("kolibri.core.deviceadmin.tasks.logger") as logger:
            perform_vacuum()
        self.assertEqual(
            logger.error.call_args_list,
            [],
            "vacuum failed and was swallowed: {}".format(logger.error.call_args_list),
        )

    def test_vacuum_covers_every_sqlite_database(self):
        with patch("kolibri.core.deviceadmin.tasks._optimize_sqlite_db") as optimize:
            perform_vacuum()
        vacuumed = sorted(call[0][0] for call in optimize.call_args_list)
        self.assertEqual(vacuumed, sorted(db.connections))

    def test_vacuum_of_a_named_database_touches_only_that_one(self):
        with patch("kolibri.core.deviceadmin.tasks._optimize_sqlite_db") as optimize:
            perform_vacuum(db.DEFAULT_DB_ALIAS)
        vacuumed = [call[0][0] for call in optimize.call_args_list]
        self.assertEqual(vacuumed, [db.DEFAULT_DB_ALIAS])
