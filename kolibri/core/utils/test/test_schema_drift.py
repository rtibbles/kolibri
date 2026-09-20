import copy
import unittest
import uuid
from contextlib import contextmanager

from django.conf import settings
from django.db import connection
from django.db import connections
from django.db import IntegrityError
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder
from django.db.utils import OperationalError
from django.test import SimpleTestCase
from django.test import TestCase
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from mock import MagicMock
from mock import patch

import kolibri
from kolibri.core.auth.models import Facility
from kolibri.core.auth.models import FacilityUser
from kolibri.core.content.models import ContentDownloadRequest
from kolibri.core.content.models import ContentNode
from kolibri.core.content.models import ContentRequest
from kolibri.core.content.models import ContentRequestReason
from kolibri.core.content.models import ContentRequestStatus
from kolibri.core.content.models import Language
from kolibri.core.device.models import DeviceSettings
from kolibri.core.device.models import DeviceStatus
from kolibri.core.device.models import LearnerDeviceStatus
from kolibri.core.device.models import OSUser
from kolibri.core.device.models import UserSyncStatus
from kolibri.core.device.utils import LANDING_PAGE_LEARN
from kolibri.core.device.utils import LANDING_PAGE_SIGN_IN
from kolibri.core.discovery.models import PinnedDevice
from kolibri.core.notifications.models import LearnerProgressNotification
from kolibri.core.utils import schema_drift
from kolibri.core.utils.schema_drift import _find_schema_drift
from kolibri.core.utils.schema_drift import _repair_database
from kolibri.core.utils.schema_drift import _repair_database_quick_check
from kolibri.core.utils.schema_drift import repair_schema_drift
from kolibri.core.utils.schema_drift import repair_schema_drift_quick_check
from kolibri.utils import main


class SchemaDriftVendorTestCase(TestCase):
    """
    Runs on every backend, unlike the case below: on a PostgreSQL installation this
    is the only coverage of the repair, and asserting the real vendor's behaviour is
    the point of it.
    """

    def _captured_sql(self, captured):
        return [query["sql"] for query in captured.captured_queries]

    def test_does_nothing_on_a_non_sqlite_database(self):
        # not one introspection query: the whole sweep is skipped, not merely the writes,
        # and with it the reconciliation of migration records it ends in. Patching vendor
        # is a no-op on a PostgreSQL run, where this asserts the real backend's behaviour
        with patch.object(connection, "vendor", "postgresql"):
            with CaptureQueriesContext(connection) as captured:
                repair_schema_drift()

        self.assertEqual(self._captured_sql(captured), [])

    def test_checks_nothing_on_a_non_sqlite_database(self):
        # the entry point every startup reaches: not even the fingerprint is looked for,
        # so a PostgreSQL installation pays one attribute read for all of them
        with patch.object(connection, "vendor", "postgresql"):
            with CaptureQueriesContext(connection) as captured:
                repair_schema_drift_quick_check()

        self.assertEqual(self._captured_sql(captured), [])


class ConnectionToRepairTestCase(SimpleTestCase):
    """
    The connection lifecycle the sweep wraps each database's repair in, which startup
    drives against connections that are usually closed and stay unused.
    """

    def _connections(self, **attributes):
        return {
            alias: MagicMock(vendor="sqlite", **attributes)
            for alias in settings.DATABASES
        }

    @patch.object(schema_drift, "_repair_database")
    def test_closes_the_connections_it_opened(self, repair):
        connections = self._connections(connection=None)

        with patch.object(schema_drift, "connections", connections):
            repair_schema_drift()

        for opened in connections.values():
            opened.close.assert_called_once_with()

    @patch.object(schema_drift, "_repair_database")
    def test_leaves_already_open_connections_open(self, repair):
        # the migrate path reaches this with every connection open and warm
        connections = self._connections()

        with patch.object(schema_drift, "connections", connections):
            repair_schema_drift()

        for opened in connections.values():
            opened.close.assert_not_called()

    @patch.object(schema_drift, "_repair_database", side_effect=Exception("boom"))
    def test_contains_a_failure_and_carries_on_to_the_next_database(self, repair):
        connections = self._connections(connection=None)

        with patch.object(schema_drift, "connections", connections):
            with patch.object(schema_drift.logger, "exception") as logged_exception:
                repair_schema_drift()

        self.assertEqual(repair.call_count, len(settings.DATABASES))
        self.assertEqual(logged_exception.call_count, len(settings.DATABASES))
        for opened in connections.values():
            opened.close.assert_called_once_with()

    @patch.object(schema_drift, "_repair_database")
    def test_contains_a_failure_to_close(self, repair):
        # SQLite refuses a close it cannot finalise, and that must not be the thing that
        # stops a boot the repair itself was contained to protect
        connections = self._connections(connection=None)
        for opened in connections.values():
            opened.close.side_effect = OperationalError("unable to close")

        with patch.object(schema_drift, "connections", connections):
            with patch.object(schema_drift.logger, "exception") as logged_exception:
                repair_schema_drift()

        self.assertEqual(logged_exception.call_count, len(settings.DATABASES))


@unittest.skipUnless(
    connection.vendor == "sqlite",
    "the damage these tests induce is a SQLite table rebuild, and the repair runs on no other backend",
)
class SchemaDriftTestCase(TransactionTestCase):
    """
    Tests for _find_schema_drift, which compares the physical schema of a database
    against the state built from the migration graph, and for repair_schema_drift,
    which puts back what it reports as missing.

    Each repair is asserted through what the database will and will not accept once
    it has run: a restored column takes a write, a restored unique constraint refuses
    a duplicate, a restored NOT NULL refuses a NULL. Indexes have no such surface and
    are the one kind asserted by introspection.
    """

    # startup sweeps every database, and the secondary ones hold only the models
    # their router allows
    databases = "__all__"

    # ------------------------------------------------------------------
    # damage
    # ------------------------------------------------------------------

    @contextmanager
    def _damaged_schema(self, damage, restore):
        """
        Apply damage to the schema and reverse it on the way out. SQLite DDL is not
        rolled back by transactional teardown, so unrestored damage poisons later tests.
        """
        with connection.schema_editor() as editor:
            damage(editor)
        try:
            yield
        finally:
            with connection.schema_editor() as editor:
                restore(editor)

    @contextmanager
    def _repairable(self, model, damage, restore):
        """
        Apply damage, and on the way out restore only what the repair under test left
        undone on this model, so a repair that does nothing cannot poison later tests.
        """
        with connection.schema_editor() as editor:
            damage(editor)
        try:
            yield
        finally:
            # keyed on this model, not on any drift at all, so that damage another
            # context manager is still holding open does not read as this one's
            label = model._meta.label
            unrepaired = [
                drift
                for drift in _find_schema_drift(connection)
                if drift.model._meta.label == label
            ]
            if unrepaired:
                with connection.schema_editor() as editor:
                    restore(editor)

    def _removed_field(self, model, field_name):
        field = model._meta.get_field(field_name)
        return self._damaged_schema(
            lambda editor: editor.remove_field(model, field),
            lambda editor: editor.add_field(model, field),
        )

    def _stale_rebuild(
        self, model, drop=(), loosen=(), drop_unique=(), drop_unique_together=False
    ):
        """
        Rebuild the table from a stale field list, as a migrate against stale state
        does: the dropped columns vanish, the loosened ones revert to nullable, the
        ones that lost their unique lose it, and the unique constraints of the stale
        state are the ones that survive. Restoring recreates the table wholesale, which
        is correct however far the repair got.

        Only fields declared on the concrete model can be dropped: the rebuild renders
        a dummy model from the same bases, so abstract base fields come back anyway.
        """
        dropped = [model._meta.get_field(name) for name in drop]
        remaining = []
        for field in model._meta.local_concrete_fields:
            if field in dropped:
                continue
            if field.name in loosen or field.name in drop_unique:
                field = copy.deepcopy(field)
            if field.name in loosen:
                field.null = True
            if field.name in drop_unique:
                # unique is a read-only property over _unique
                field._unique = False
            remaining.append(field)
        unique_together = () if drop_unique_together else model._meta.unique_together

        def damage(editor):
            with patch.object(model._meta, "local_concrete_fields", remaining):
                with patch.object(model._meta, "unique_together", unique_together):
                    editor._remake_table(model)

        def restore(editor):
            editor.delete_model(model)
            editor.create_model(model)

        return self._damaged_schema(damage, restore)

    def _dropped_unique_together(self, model):
        field_names = model._meta.unique_together[0]
        return self._repairable(
            model,
            lambda editor: editor.alter_unique_together(model, [field_names], []),
            lambda editor: editor.alter_unique_together(model, [], [field_names]),
        )

    def _altered_nullability(self, model, field_name, null):
        field = model._meta.get_field(field_name)
        altered = copy.deepcopy(field)
        altered.null = null
        return self._repairable(
            model,
            lambda editor: editor.alter_field(model, field, altered),
            lambda editor: editor.alter_field(model, altered, field),
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _user(self):
        facility = Facility.objects.create(name="Test Facility")
        return FacilityUser.objects.create(username="learner", facility=facility)

    def _constraints(self, model):
        with connection.cursor() as cursor:
            return connection.introspection.get_constraints(
                cursor, model._meta.db_table
            )

    def _has_index(self, model, field_names):
        # an index has no behavioural surface: nothing a query can do tells a table
        # with one from a table without
        columns = [model._meta.get_field(name).column for name in field_names]
        return any(
            info["index"] and list(info["columns"]) == columns
            for info in self._constraints(model).values()
        )

    def _has_unique_constraint(self, model, field_names):
        columns = [model._meta.get_field(name).column for name in field_names]
        return any(
            info["unique"] and list(info["columns"]) == columns
            for info in self._constraints(model).values()
        )

    def _landing_page(self, pk):
        # read around DeviceSettingsManager, which caches the instance it hands out
        return (
            DeviceSettings.objects.filter(pk=pk)
            .values_list("landing_page", flat=True)
            .first()
        )

    def _logged_messages(self, logged):
        return [call[0][0] % call[0][1:] for call in logged.call_args_list]

    def _assert_blocked_rebuild(self, logged_error, table, blocker):
        """
        The pre-flight refused the rebuild, rather than the rebuild being attempted and
        its failure contained by the per-model isolation net. Both leave an error logged
        and the schema unrepaired, so only the message tells them apart.
        """
        messages = self._logged_messages(logged_error)
        blocked = [message for message in messages if "Cannot rebuild table" in message]
        self.assertEqual(len(blocked), 1, messages)
        self.assertIn(table, blocked[0])
        self.assertIn(blocker, blocked[0])
        contained = [
            message
            for message in messages
            if "Could not repair the schema of" in message
        ]
        self.assertEqual(contained, [])

    # ------------------------------------------------------------------
    # detection
    # ------------------------------------------------------------------

    def test_no_drift_on_any_migrated_database(self):
        # a false positive on a healthy installation is an error logged at every
        # startup and a repair rewriting a schema that was never damaged; the
        # secondary databases are swept too, and hold only their router's models
        for alias in settings.DATABASES:
            with patch.object(schema_drift.logger, "error") as logged_error:
                with patch.object(schema_drift.logger, "warning") as logged_warning:
                    drifts = _find_schema_drift(connections[alias])

            self.assertEqual(drifts, [], alias)
            self.assertEqual(self._logged_messages(logged_error), [], alias)
            self.assertEqual(self._logged_messages(logged_warning), [], alias)

    def test_ignores_models_routed_to_another_database(self):
        table = LearnerProgressNotification._meta.db_table
        # the router keeps this table out of the default database, so an unfiltered
        # detector would report it as a missing table
        self.assertNotIn(table, connection.introspection.table_names())

        with patch.object(schema_drift.logger, "error") as logged_error:
            drifts = _find_schema_drift(connection)

        self.assertEqual(drifts, [])
        self.assertEqual(logged_error.call_count, 0)

    def test_returns_nothing_when_migrations_are_pending(self):
        recorder = MigrationRecorder(connection)
        app, name = MigrationLoader(connection).graph.leaf_nodes()[0]
        with self._removed_field(DeviceSettings, "language_id"):
            recorder.migration_qs.filter(app=app, name=name).delete()
            try:
                self.assertEqual(_find_schema_drift(connection), [])
            finally:
                recorder.record_applied(app, name)

    def test_makes_no_changes_to_a_healthy_database(self):
        with CaptureQueriesContext(connection) as captured:
            _repair_database(connection)

        for query in captured.captured_queries:
            sql = query["sql"].lstrip().upper()
            # an allowlist, so that a statement nobody thought to forbid still fails.
            # every writing PRAGMA carries an "=", so this also catches a schema editor
            # being opened, which turns foreign key enforcement off before it does
            # anything else
            self.assertTrue(
                sql.startswith(("SELECT", "BEGIN", "COMMIT", "ROLLBACK"))
                or (sql.startswith("PRAGMA") and "=" not in sql),
                query["sql"],
            )

    def test_reports_a_missing_table_without_repairing_it(self):
        # the one damage this reports and deliberately leaves alone: creating a table
        # is a migration's job, and an empty one would look migrated while holding
        # none of the rows the operator's backup still has
        table = PinnedDevice._meta.db_table
        with self._damaged_schema(
            lambda editor: editor.delete_model(PinnedDevice),
            lambda editor: editor.create_model(PinnedDevice),
        ):
            with patch.object(schema_drift.logger, "error") as logged_error:
                _repair_database(connection)

            self.assertNotIn(table, connection.introspection.table_names())
            messages = self._logged_messages(logged_error)
            self.assertEqual(len(messages), 1, messages)
            self.assertIn(table, messages[0])
            self.assertIn(PinnedDevice._meta.label, messages[0])

    # ------------------------------------------------------------------
    # what the database has and the migration state does not
    # ------------------------------------------------------------------

    @contextmanager
    def _extra_column(self, model, column):
        # restored by recreating the table, because remove_field needs a Field and the
        # state model has none for a column it does not know about
        table = model._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(
                "ALTER TABLE {} ADD COLUMN {} varchar(32)".format(table, column)
            )
        try:
            yield
        finally:
            with connection.schema_editor() as editor:
                editor.delete_model(model)
                editor.create_model(model)

    def test_reports_a_column_the_migration_state_does_not_have(self):
        # a stale rebuild can also resurrect a column a later migration dropped, and
        # rebuilding the table would destroy it along with the data in it
        DeviceSettings.objects.create()
        table = DeviceSettings._meta.db_table

        # the nullability damage first: applying it would drop the extra column
        with self._altered_nullability(DeviceSettings, "landing_page", True):
            with self._extra_column(DeviceSettings, "leftover"):
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE {} SET leftover = 'keep me'".format(table))

                with patch.object(schema_drift.logger, "error") as logged_error:
                    _repair_database(connection)

                # reported in its own right, not only as the reason a rebuild was refused
                messages = self._logged_messages(logged_error)
                self.assertTrue(
                    any(
                        "holds columns" in message and "leftover" in message
                        for message in messages
                    ),
                    messages,
                )
                # the rebuild that would have tightened landing_page is refused rather
                # than attempted, because it would have taken the column with it
                self._assert_blocked_rebuild(logged_error, table, "leftover")
                # so landing_page is still loosened, and the column still holds its data
                DeviceSettings.objects.all().update(landing_page=None)
                with connection.cursor() as cursor:
                    cursor.execute("SELECT leftover FROM {}".format(table))
                    self.assertEqual(cursor.fetchone()[0], "keep me")

    def test_reports_an_index_the_migration_state_does_not_have(self):
        table = OSUser._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE INDEX leftover_idx ON {} (os_username, user_id)".format(table)
            )
        try:
            with patch.object(schema_drift.logger, "warning") as logged_warning:
                _repair_database(connection)

            messages = self._logged_messages(logged_warning)
            self.assertTrue(
                any("os_username" in message for message in messages), messages
            )
            # left alone: an operator may have added it to solve a real problem
            self.assertTrue(self._has_index(OSUser, ["os_username", "user"]))
        finally:
            with connection.cursor() as cursor:
                cursor.execute("DROP INDEX leftover_idx")

    # ------------------------------------------------------------------
    # missing columns
    # ------------------------------------------------------------------

    def test_repairs_a_missing_nullable_column(self):
        with self._stale_rebuild(DeviceSettings, drop=["language_id"]):
            with self.assertRaises(OperationalError):
                DeviceSettings.objects.create()

            _repair_database(connection)

            device_settings = DeviceSettings.objects.create(language_id="en")
            self.assertEqual(
                DeviceSettings.objects.filter(pk=device_settings.pk)
                .values_list("language_id", flat=True)
                .first(),
                "en",
            )

    def test_repairs_two_missing_columns_on_one_model(self):
        # a rebuild based repair fails here: its INSERT ... SELECT names every column of
        # the state model while reading a table that is missing two of them
        with self._stale_rebuild(DeviceSettings, drop=["language_id", "landing_page"]):
            _repair_database(connection)

            device_settings = DeviceSettings.objects.create(
                language_id="en", landing_page=LANDING_PAGE_LEARN
            )
            self.assertEqual(self._landing_page(device_settings.pk), LANDING_PAGE_LEARN)

    def test_repairs_a_missing_not_null_column_and_backfills_existing_rows(self):
        # landing_page is NOT NULL, so the rows already in the table cannot keep the
        # NULL an ADD COLUMN leaves them with
        device_settings = DeviceSettings.objects.create()
        DeviceSettings.objects.filter(pk=device_settings.pk).update(
            landing_page=LANDING_PAGE_LEARN
        )

        with self._stale_rebuild(DeviceSettings, drop=["landing_page"]):
            _repair_database(connection)

            # the field's default, the only value the repair has to fill a row with
            self.assertEqual(
                self._landing_page(device_settings.pk), LANDING_PAGE_SIGN_IN
            )
            with self.assertRaises(IntegrityError):
                DeviceSettings.objects.filter(pk=device_settings.pk).update(
                    landing_page=None
                )

    def test_repairs_a_missing_foreign_key_column(self):
        # ADD COLUMN is the only route that has to spell the reference out itself, and
        # a reference it failed to spell out is invisible until a row dangles
        facility = Facility.objects.create(name="Test Facility")

        with self._stale_rebuild(DeviceSettings, drop=["default_facility"]):
            _repair_database(connection)

            device_settings = DeviceSettings.objects.create(default_facility=facility)
            with self.assertRaises(IntegrityError):
                DeviceSettings.objects.filter(pk=device_settings.pk).update(
                    default_facility_id=uuid.uuid4().hex
                )

    def test_repairs_a_missing_column_carrying_an_index(self):
        # the index over the column is only reported once the column itself is back
        with self._stale_rebuild(OSUser, drop=["os_username"]):
            _repair_database(connection)

            user = self._user()
            OSUser.objects.create(user=user, os_username="learner")
            self.assertTrue(self._has_index(OSUser, ["os_username"]))

    def test_repairs_a_missing_column_carrying_a_unique_constraint(self):
        # a re-added column lands last, which moves every foreign key's position, and
        # it carries a unique_together that only comes back with it
        user = self._user()
        with self._stale_rebuild(
            LearnerDeviceStatus, drop=["user"], drop_unique_together=True
        ):
            _repair_database(connection)

            LearnerDeviceStatus.save_learner_status(
                user.id, DeviceStatus.InsufficientStorage
            )
            self.assertTrue(
                self._has_unique_constraint(
                    LearnerDeviceStatus, LearnerDeviceStatus._meta.unique_together[0]
                )
            )

    def test_repairs_a_missing_auto_now_add_column(self):
        user = self._user()
        LearnerDeviceStatus.save_learner_status(
            user.id, DeviceStatus.InsufficientStorage
        )

        with self._stale_rebuild(LearnerDeviceStatus, drop=["created_at"]):
            _repair_database(connection)

            created_at = list(
                LearnerDeviceStatus.objects.values_list("created_at", flat=True)
            )

        # NOT NULL, so the existing row takes the only value available, the time of
        # the repair
        self.assertEqual(len(created_at), 1)
        self.assertIsNotNone(created_at[0])

    def test_repair_invents_no_data(self):
        """
        A restored nullable column holds what a normally migrated database holds there,
        NULL: the state model's default is today's, and need not be the one declared by
        the migration that added the column. Only a column the database cannot leave
        NULL is backfilled.
        """
        facility = Facility.objects.create(name="Test Facility")
        for source_model in ("first", "second", "third"):
            ContentDownloadRequest.objects.create(
                facility=facility,
                source_model=source_model,
                source_id=uuid.uuid4().hex,
                contentnode_id=uuid.uuid4().hex,
                reason=ContentRequestReason.UserInitiated,
                status=ContentRequestStatus.Pending,
            )
        before = self._row_fingerprint(ContentRequest)
        restored = ("priority", "requested_at")

        with self._stale_rebuild(ContentRequest, drop=list(restored)):
            _repair_database(connection)
            after = self._row_fingerprint(ContentRequest)

        self.assertEqual(sorted(after), sorted(before))
        for pk, row in after.items():
            self.assertEqual(
                {c: v for c, v in row.items() if c not in restored},
                {c: v for c, v in before[pk].items() if c not in restored},
            )
            # priority is nullable, so NULL is what the missed migration would have left
            self.assertIsNone(row["priority"])
        # requested_at cannot hold NULL, so every row takes the field's default, the one
        # value it evaluates to at the time of the repair
        backfilled = {row["requested_at"] for row in after.values()}
        self.assertEqual(len(backfilled), 1)
        self.assertNotIn(
            backfilled.pop(), {row["requested_at"] for row in before.values()}
        )

    def _row_fingerprint(self, model):
        """
        Every row of a model's table as a primary key keyed mapping of column to
        value. Read column by column off the physical table rather than through the
        ORM, so a column the repair has not put back is simply absent instead of
        being papered over by the field's default.
        """
        table = model._meta.db_table
        with connection.cursor() as cursor:
            columns = [
                info.name
                for info in connection.introspection.get_table_description(
                    cursor, table
                )
            ]
            cursor.execute("SELECT {} FROM {}".format(", ".join(columns), table))
            rows = cursor.fetchall()
        pk = columns.index(model._meta.pk.column)
        return {row[pk]: dict(zip(columns, row)) for row in rows}

    # ------------------------------------------------------------------
    # missing indexes
    # ------------------------------------------------------------------

    def test_repairs_a_missing_meta_index(self):
        index = ContentNode._meta.indexes[0]
        with self._repairable(
            ContentNode,
            lambda editor: editor.remove_index(ContentNode, index),
            lambda editor: editor.add_index(ContentNode, index),
        ):
            self.assertFalse(self._has_index(ContentNode, index.fields))

            _repair_database(connection)

            self.assertTrue(self._has_index(ContentNode, index.fields))

    def test_repairs_a_missing_index_together(self):
        field_names = ContentNode._meta.index_together[0]
        with self._repairable(
            ContentNode,
            lambda editor: editor.alter_index_together(ContentNode, [field_names], []),
            lambda editor: editor.alter_index_together(ContentNode, [], [field_names]),
        ):
            self.assertFalse(self._has_index(ContentNode, field_names))

            _repair_database(connection)

            self.assertTrue(self._has_index(ContentNode, field_names))

    def test_repairs_a_missing_field_index(self):
        indexed = OSUser._meta.get_field("os_username")
        not_indexed = copy.deepcopy(indexed)
        not_indexed.db_index = False
        with self._repairable(
            OSUser,
            lambda editor: editor.alter_field(OSUser, indexed, not_indexed),
            lambda editor: editor.alter_field(OSUser, not_indexed, indexed),
        ):
            self.assertFalse(self._has_index(OSUser, ["os_username"]))

            _repair_database(connection)

            self.assertTrue(self._has_index(OSUser, ["os_username"]))

    # ------------------------------------------------------------------
    # missing unique constraints
    # ------------------------------------------------------------------

    def test_repairs_a_missing_unique_together(self):
        user = self._user()
        instance_id = uuid.uuid4().hex

        with self._dropped_unique_together(PinnedDevice):
            # the database takes the duplicate the model forbids
            PinnedDevice.objects.create(user=user, instance_id=instance_id)
            PinnedDevice.objects.create(user=user, instance_id=instance_id).delete()

            _repair_database(connection)

            with self.assertRaises(IntegrityError):
                PinnedDevice.objects.create(user=user, instance_id=instance_id)

    def test_repairs_a_missing_unique_together_on_an_m2m_through_table(self):
        # an auto-created through model is invisible to get_models() by default, and
        # its unique_together is the only thing keeping duplicate rows out. Asserted by
        # introspection because the model has no manager to write duplicates through.
        through = ContentNode._meta.get_field("tags").remote_field.through
        unique_together = through._meta.unique_together[0]

        with self._dropped_unique_together(through):
            self.assertFalse(self._has_unique_constraint(through, unique_together))

            _repair_database(connection)

            self.assertTrue(self._has_unique_constraint(through, unique_together))

    def test_repairs_a_missing_unique_field(self):
        # a stale rebuild drops a single column unique too, and a OneToOneField that
        # takes a second row turns .get(user=…) into MultipleObjectsReturned
        user = self._user()

        with self._stale_rebuild(UserSyncStatus, drop_unique=["user"]):
            UserSyncStatus.objects.create(user=user)

            _repair_database(connection)

            with self.assertRaises(IntegrityError):
                UserSyncStatus.objects.create(user=user)

    def test_repairs_what_it_can_when_a_rebuild_is_refused(self):
        user = self._user()
        instance_id = uuid.uuid4().hex

        with self._stale_rebuild(
            PinnedDevice, loosen=["instance_id"], drop_unique_together=True
        ):
            with self._extra_column(PinnedDevice, "leftover"):
                with patch.object(schema_drift.logger, "error"):
                    _repair_database(connection)

                pinned = PinnedDevice.objects.create(user=user, instance_id=instance_id)
                # the rebuild really was refused: the column it would have tightened
                # is loose. Put the value back, or the NULL collides with nothing and
                # the constraint below has nothing to refuse
                PinnedDevice.objects.filter(pk=pinned.pk).update(instance_id=None)
                PinnedDevice.objects.filter(pk=pinned.pk).update(
                    instance_id=instance_id
                )
                # the constraint no blocker applied to came back anyway
                with self.assertRaises(IntegrityError):
                    PinnedDevice.objects.create(user=user, instance_id=instance_id)

    def test_leaves_a_violated_unique_together_for_the_operator_to_resolve(self):
        user = self._user()
        instance_id = uuid.uuid4().hex

        with self._dropped_unique_together(PinnedDevice):
            PinnedDevice.objects.create(user=user, instance_id=instance_id)
            duplicate = PinnedDevice.objects.create(user=user, instance_id=instance_id)
            try:
                with patch.object(schema_drift.logger, "error") as logged_error:
                    _repair_database(connection)

                # still reported, which is the visible and actionable outcome
                self.assertTrue(_find_schema_drift(connection))
                messages = self._logged_messages(logged_error)
                self.assertEqual(len(messages), 1, messages)
                self.assertIn(PinnedDevice._meta.label, messages[0])
                self.assertIn("instance_id", messages[0])
                self.assertIn("2 rows are duplicates", messages[0])

                # the row an operator has to resolve by hand, after which the next
                # startup repairs what this one refused
                duplicate.delete()
                _repair_database(connection)

                with self.assertRaises(IntegrityError):
                    PinnedDevice.objects.create(user=user, instance_id=instance_id)
            finally:
                PinnedDevice.objects.all().delete()

    def test_leaves_a_violated_unique_together_alone_on_a_model_with_meta_ordering(
        self,
    ):
        # Meta.ordering joins the GROUP BY of the duplicate count unless it is cleared,
        # which hides every duplicate: the pre-flight then passes and the rebuild fails
        facility = Facility.objects.create(name="Test Facility")
        unique_together = ContentRequest._meta.unique_together[0]
        self.assertTrue(ContentRequest._meta.ordering)

        # loosened as well as dropped, so the repair has a rebuild to refuse: a bare
        # unique constraint is added in place, and its failure is contained rather than
        # blocked by the pre-flight
        with self._stale_rebuild(
            ContentRequest, loosen=["source_model"], drop_unique_together=True
        ):
            duplicated = dict(
                facility=facility,
                source_model="facilityuser",
                source_id=uuid.uuid4().hex,
                contentnode_id=uuid.uuid4().hex,
                channel_version=1,
                reason=ContentRequestReason.UserInitiated,
                status=ContentRequestStatus.Pending,
            )
            ContentDownloadRequest.objects.create(**duplicated)
            duplicate = ContentDownloadRequest.objects.create(**duplicated)

            with patch.object(schema_drift.logger, "error") as logged_error:
                _repair_database(connection)

            self._assert_blocked_rebuild(
                logged_error, ContentRequest._meta.db_table, "2 rows are duplicates"
            )
            self.assertFalse(
                self._has_unique_constraint(ContentRequest, unique_together)
            )

            # the row an operator has to resolve by hand
            duplicate.delete()
            _repair_database(connection)

            self.assertTrue(
                self._has_unique_constraint(ContentRequest, unique_together)
            )
            self.assertEqual(_find_schema_drift(connection), [])

    # ------------------------------------------------------------------
    # nullability
    # ------------------------------------------------------------------

    def test_repairs_a_column_loosened_to_nullable(self):
        device_settings = DeviceSettings.objects.create()
        rows = DeviceSettings.objects.filter(pk=device_settings.pk)

        with self._altered_nullability(DeviceSettings, "landing_page", True):
            # the database takes the NULL the model forbids, and the repair has to
            # fill it before it can tighten the column back
            rows.update(landing_page=None)

            _repair_database(connection)

            self.assertEqual(
                self._landing_page(device_settings.pk), LANDING_PAGE_SIGN_IN
            )
            with self.assertRaises(IntegrityError):
                rows.update(landing_page=None)

    def test_repairs_a_column_tightened_to_not_null(self):
        with self._altered_nullability(DeviceSettings, "language_id", False):
            device_settings = DeviceSettings.objects.create(language_id="en")
            rows = DeviceSettings.objects.filter(pk=device_settings.pk)
            # the database refuses the NULL the model allows
            with self.assertRaises(IntegrityError):
                rows.update(language_id=None)

            _repair_database(connection)

            rows.update(language_id=None)
            self.assertIsNone(rows.values_list("language_id", flat=True).first())

    def test_writes_nothing_when_a_rebuild_is_refused(self):
        # the pre-flight runs before the fill, so a rebuild that was never going to be
        # attempted leaves the rows the operator is about to inspect as it found them
        device_settings = DeviceSettings.objects.create()

        # the nullability damage first: applying it would drop the extra column
        with self._altered_nullability(DeviceSettings, "landing_page", True):
            DeviceSettings.objects.filter(pk=device_settings.pk).update(
                landing_page=None
            )
            with self._extra_column(DeviceSettings, "leftover"):
                with patch.object(schema_drift.logger, "error"):
                    _repair_database(connection)

                self.assertIsNone(self._landing_page(device_settings.pk))

    def test_leaves_unfillable_nulls_for_the_operator_to_resolve(self):
        # lang_code has no default, so its NULL cannot be filled, and a rebuild for
        # lang_direction would reinstate NOT NULL on lang_code and fail on the same row
        with self._stale_rebuild(Language, loosen=["lang_code", "lang_direction"]):
            Language.objects.create(id="xx", lang_code="xx")
            Language.objects.filter(pk="xx").update(lang_code=None)
            try:
                with patch.object(schema_drift.logger, "error") as logged_error:
                    _repair_database(connection)

                messages = self._logged_messages(logged_error)
                self.assertTrue(
                    any("1 rows hold NULL" in message for message in messages), messages
                )
                self._assert_blocked_rebuild(
                    logged_error, Language._meta.db_table, "NULL in lang_code"
                )
                # neither column was tightened: the rebuild that would have tightened
                # lang_direction reinstates NOT NULL on lang_code too, so it is skipped
                # whole. Still reported, for the next startup to retry.
                Language.objects.filter(pk="xx").update(lang_direction=None)
                self.assertTrue(_find_schema_drift(connection))

                # the row an operator has to resolve by hand
                Language.objects.filter(pk="xx").delete()
                _repair_database(connection)

                language = Language.objects.create(id="yy", lang_code="yy")
                with self.assertRaises(IntegrityError):
                    Language.objects.filter(pk=language.pk).update(lang_direction=None)
                self.assertEqual(_find_schema_drift(connection), [])
            finally:
                Language.objects.all().delete()

    # ------------------------------------------------------------------
    # the fingerprint that gates the every startup check
    # ------------------------------------------------------------------

    @contextmanager
    def _duplicate_migration_record(self):
        """
        Record an already applied migration a second time, as two processes migrating at
        once do: the recorder's table has no unique constraint over (app, name).
        """
        recorder = MigrationRecorder(connection)
        app, name = MigrationLoader(connection).graph.leaf_nodes()[0]
        recorder.record_applied(app, name)
        try:
            yield (app, name)
        finally:
            recorded = recorder.migration_qs.filter(app=app, name=name)
            recorded.exclude(pk=recorded.first().pk).delete()

    def test_checks_nothing_without_the_fingerprint_of_a_concurrent_migration(self):
        # detection is an introspection of every model, and on a healthy installation
        # every startup of it would find nothing
        with self._stale_rebuild(DeviceSettings, drop=["language_id"]):
            with CaptureQueriesContext(connection) as captured:
                _repair_database_quick_check(connection)

            # the damage is left alone, for two metadata queries: does the recorder have
            # a table, and does it hold the same migration twice
            self.assertTrue(_find_schema_drift(connection))
            self.assertEqual(len(captured.captured_queries), 2)
            self.assertNotIn(
                DeviceSettings._meta.db_table,
                " ".join(query["sql"] for query in captured.captured_queries),
            )

    def test_repairs_a_database_that_was_migrated_concurrently(self):
        with self._stale_rebuild(DeviceSettings, drop=["language_id"]):
            with self._duplicate_migration_record():
                _repair_database_quick_check(connection)

            self.assertEqual(_find_schema_drift(connection), [])
            DeviceSettings.objects.create(language_id="en")

    def _recorded_migrations(self):
        return list(
            MigrationRecorder(connection).migration_qs.values_list("app", "name")
        )

    def test_reconciles_duplicate_migration_records_once_nothing_needs_repairing(self):
        # left in place they would cost every later startup a full introspection
        with self._duplicate_migration_record():
            recorded = self._recorded_migrations()

            _repair_database(connection)

            reconciled = self._recorded_migrations()

        # the duplicate is gone and every migration is still recorded exactly once, which
        # is what stops Django from applying any of them again
        self.assertEqual(len(reconciled), len(recorded) - 1)
        self.assertEqual(sorted(set(reconciled)), sorted(set(recorded)))
        self.assertEqual(len(reconciled), len(set(reconciled)))

    def test_keeps_duplicate_migration_records_until_a_later_sweep_finds_no_drift(self):
        # the fingerprint outlives the repair by one sweep, so the evidence is only
        # dropped once an independent detection pass agrees the repair worked
        with self._stale_rebuild(DeviceSettings, drop=["language_id"]):
            with self._duplicate_migration_record():
                _repair_database(connection)
                self.assertEqual(_find_schema_drift(connection), [])
                repaired = self._recorded_migrations()

                _repair_database(connection)
                reconciled = self._recorded_migrations()

        self.assertEqual(len(repaired), len(set(repaired)) + 1)
        self.assertEqual(len(reconciled), len(set(reconciled)))

    def test_keeps_duplicate_migration_records_while_migrations_are_unapplied(self):
        # a migration still to be applied may yet be recorded twice itself
        recorder = MigrationRecorder(connection)
        with self._duplicate_migration_record() as duplicated:
            app, name = next(
                node
                for node in MigrationLoader(connection).graph.leaf_nodes()
                if node != duplicated
            )
            recorder.migration_qs.filter(app=app, name=name).delete()
            try:
                _repair_database(connection)
                recorded = self._recorded_migrations()
            finally:
                recorder.record_applied(app, name)

        self.assertEqual(len(recorded), len(set(recorded)) + 1)

    # ------------------------------------------------------------------
    # the startup path, and failure containment
    # ------------------------------------------------------------------

    def test_startup_repairs_a_damaged_database(self):
        """
        The repair as startup runs it: over every database Kolibri opens, through the
        blanket handler that keeps a failure from stopping a boot, and against the
        connections Django hands out rather than one the test picked.
        """
        with self._stale_rebuild(
            DeviceSettings, drop=["language_id"], loosen=["landing_page"]
        ):
            # migrate has nothing to do here, as it had nothing to do in the incident:
            # every migration is recorded, only the schema they built is missing
            with patch.object(main, "call_command"):
                with patch.object(schema_drift.logger, "exception") as logged_exception:
                    main._migrate_databases()

            # the containment logs and carries on, so a repair that blew up on any of
            # the databases would otherwise show up only as damage left
            self.assertEqual(logged_exception.call_args_list, [])
            self.assertEqual(_find_schema_drift(connection), [])

            device_settings = DeviceSettings.objects.create(language_id="en")
            with self.assertRaises(IntegrityError):
                DeviceSettings.objects.filter(pk=device_settings.pk).update(
                    landing_page=None
                )

    def test_startup_repairs_a_damaged_database_without_an_upgrade(self):
        """
        The startup that migrates nothing: on an installation already on this version
        check_database_is_migrated succeeds, no migration runs, and this branch is the
        only thing that will look at the schema again. Left to _migrate_databases, a
        repair the operator had to resolve by hand would never be retried.
        """
        with self._stale_rebuild(
            DeviceSettings, drop=["language_id"], loosen=["landing_page"]
        ):
            with self._duplicate_migration_record():
                # everything either side of the database check, which is left real: that
                # it succeeds on a damaged database is the reason this branch exists
                with patch.object(main, "run_plugin_updates"):
                    with patch.object(main, "check_django_stack_ready"):
                        with patch.object(main, "_upgrades_after_django_setup"):
                            main._run_updates(False, kolibri.__version__)

            self.assertEqual(_find_schema_drift(connection), [])

            device_settings = DeviceSettings.objects.create(language_id="en")
            with self.assertRaises(IntegrityError):
                DeviceSettings.objects.filter(pk=device_settings.pk).update(
                    landing_page=None
                )

    def test_repairs_a_secondary_database(self):
        # every other test here drives the default connection, and a repair that only
        # ever reached that one would leave five databases unhealed: the sweep of a
        # secondary database sees only the two models its router assigns to it
        notifications = connections["notifications"]
        field = LearnerProgressNotification._meta.get_field("quiz_num_correct")
        with notifications.schema_editor() as editor:
            editor.remove_field(LearnerProgressNotification, field)
        try:
            self.assertTrue(_find_schema_drift(notifications))

            _repair_database(notifications)

            self.assertEqual(_find_schema_drift(notifications), [])
            # nullable, so the repair leaves it holding what a migration would have
            notification = LearnerProgressNotification.objects.create(
                user_id=uuid.uuid4().hex, classroom_id=uuid.uuid4().hex
            )
            self.assertIsNone(
                LearnerProgressNotification.objects.filter(pk=notification.pk)
                .values_list("quiz_num_correct", flat=True)
                .first()
            )
        finally:
            if _find_schema_drift(notifications):
                with notifications.schema_editor() as editor:
                    editor.add_field(LearnerProgressNotification, field)

    def test_repairs_nothing_while_a_referenced_table_is_missing(self):
        # SQLite reports every row referencing a dropped table as a foreign key
        # violation, and the schema editor checks the whole database on the way out,
        # so nothing on this database can be repaired until that table is back
        user = self._user()
        LearnerDeviceStatus.save_learner_status(
            user.id, DeviceStatus.InsufficientStorage
        )

        with self._stale_rebuild(DeviceSettings, loosen=["landing_page"]):
            # dropped behind Django's back, because the schema editor cannot drop a
            # referenced table either: its own exit check sees the rows left dangling
            with connection.constraint_checks_disabled():
                with connection.cursor() as cursor:
                    cursor.execute("DROP TABLE {}".format(FacilityUser._meta.db_table))
            try:
                with patch.object(schema_drift.logger, "error") as logged_error:
                    _repair_database(connection)

                messages = self._logged_messages(logged_error)
                self.assertIn(FacilityUser._meta.db_table, messages[0])
                # contained, so startup continues on a usable connection
                self.assertTrue(
                    any(
                        "Could not repair the schema of" in message
                        for message in messages
                    ),
                    messages,
                )
                self.assertFalse(connection.in_atomic_block)
                self.assertTrue(connection.get_autocommit())
                # and nothing was repaired, on this or any other model
                device_settings = DeviceSettings.objects.create()
                DeviceSettings.objects.filter(pk=device_settings.pk).update(
                    landing_page=None
                )
                # the blast radius: SQLite refuses any write it would have to check
                # against the missing table, so every referencing table is stuck too
                with self.assertRaises(OperationalError):
                    LearnerDeviceStatus.objects.all().delete()
            finally:
                # the dangling rows first, or recreating the table empty leaves them
                # dangling still and the teardown fails the same check; and with
                # enforcement on, they cannot be deleted while the table is missing
                with connection.constraint_checks_disabled():
                    LearnerDeviceStatus.objects.all().delete()
                with connection.schema_editor() as editor:
                    editor.create_model(FacilityUser)

    def test_leaves_the_connection_usable_when_the_foreign_key_check_fails(self):
        # the schema editor checks foreign keys before leaving its atomic block, so a
        # violation predating this repair strands the connection in an open transaction,
        # and everything initialize() does afterwards would roll back at process exit
        user = self._user()

        with self._stale_rebuild(DeviceSettings, drop=["language_id"]):
            with connection.constraint_checks_disabled():
                FacilityUser.objects.filter(pk=user.pk).update(
                    facility_id=uuid.uuid4().hex
                )

            try:
                with patch.object(schema_drift.logger, "error") as logged_error:
                    _repair_database(connection)

                self.assertTrue(self._logged_messages(logged_error))
                self.assertFalse(connection.in_atomic_block)
                self.assertTrue(connection.get_autocommit())
                # a query on the connection the rest of initialize() goes on to use
                self.assertEqual(DeviceSettings.objects.count(), 0)
                with connection.cursor() as cursor:
                    cursor.execute("PRAGMA foreign_keys")
                    self.assertEqual(cursor.fetchone()[0], 1)
            finally:
                # the in memory instance still holds the facility the queryset
                # update replaced in the database
                with connection.constraint_checks_disabled():
                    FacilityUser.objects.filter(pk=user.pk).update(
                        facility_id=user.facility_id
                    )

    def test_repairs_other_models_when_one_model_fails(self):
        # each model is repaired through a schema editor of its own, so the transaction
        # a failure rolls back is that model's alone. Raised as the lock error of the
        # incident, two concurrent processes, which must leave Kolibri booting
        add_column = schema_drift.SchemaDrift._add_column

        def failing(self, schema_editor, field):
            if self.model._meta.label == OSUser._meta.label:
                raise OperationalError("database is locked")
            return add_column(self, schema_editor, field)

        with self._stale_rebuild(OSUser, drop=["os_username"]):
            with self._stale_rebuild(DeviceSettings, drop=["language_id"]):
                # a private symbol, because a failure of one model's repair alone cannot
                # be induced through the public surface
                with patch.object(schema_drift.SchemaDrift, "_add_column", failing):
                    with patch.object(schema_drift.logger, "error") as logged_error:
                        _repair_database(connection)

                self.assertEqual(logged_error.call_count, 1)
                DeviceSettings.objects.create(language_id="en")
                with self.assertRaises(OperationalError):
                    OSUser.objects.create(user=self._user(), os_username="learner")
