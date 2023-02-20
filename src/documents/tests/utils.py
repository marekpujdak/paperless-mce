import os
import shutil
import tempfile
from collections import namedtuple
from contextlib import contextmanager
from os import PathLike
from pathlib import Path
from typing import Union
from unittest import mock

from django.apps import apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import override_settings
from django.test import TransactionTestCase


def setup_directories():

    dirs = namedtuple("Dirs", ())

    dirs.data_dir = tempfile.mkdtemp()
    dirs.scratch_dir = tempfile.mkdtemp()
    dirs.media_dir = tempfile.mkdtemp()
    dirs.consumption_dir = tempfile.mkdtemp()
    dirs.static_dir = tempfile.mkdtemp()
    dirs.index_dir = os.path.join(dirs.data_dir, "index")
    dirs.originals_dir = os.path.join(dirs.media_dir, "documents", "originals")
    dirs.thumbnail_dir = os.path.join(dirs.media_dir, "documents", "thumbnails")
    dirs.archive_dir = os.path.join(dirs.media_dir, "documents", "archive")
    dirs.logging_dir = os.path.join(dirs.data_dir, "log")

    os.makedirs(dirs.index_dir, exist_ok=True)
    os.makedirs(dirs.originals_dir, exist_ok=True)
    os.makedirs(dirs.thumbnail_dir, exist_ok=True)
    os.makedirs(dirs.archive_dir, exist_ok=True)

    os.makedirs(dirs.logging_dir, exist_ok=True)

    dirs.settings_override = override_settings(
        DATA_DIR=dirs.data_dir,
        SCRATCH_DIR=dirs.scratch_dir,
        MEDIA_ROOT=dirs.media_dir,
        ORIGINALS_DIR=dirs.originals_dir,
        THUMBNAIL_DIR=dirs.thumbnail_dir,
        ARCHIVE_DIR=dirs.archive_dir,
        CONSUMPTION_DIR=dirs.consumption_dir,
        LOGGING_DIR=dirs.logging_dir,
        INDEX_DIR=dirs.index_dir,
        STATIC_ROOT=dirs.static_dir,
        MODEL_FILE=os.path.join(dirs.data_dir, "classification_model.pickle"),
        MEDIA_LOCK=os.path.join(dirs.media_dir, "media.lock"),
    )
    dirs.settings_override.enable()

    return dirs


def remove_dirs(dirs):
    shutil.rmtree(dirs.media_dir, ignore_errors=True)
    shutil.rmtree(dirs.data_dir, ignore_errors=True)
    shutil.rmtree(dirs.scratch_dir, ignore_errors=True)
    shutil.rmtree(dirs.consumption_dir, ignore_errors=True)
    shutil.rmtree(dirs.static_dir, ignore_errors=True)
    dirs.settings_override.disable()


@contextmanager
def paperless_environment():
    dirs = None
    try:
        dirs = setup_directories()
        yield dirs
    finally:
        if dirs:
            remove_dirs(dirs)


class DirectoriesMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dirs = None

    def setUp(self) -> None:
        self.dirs = setup_directories()
        super().setUp()

    def tearDown(self) -> None:
        super().tearDown()
        remove_dirs(self.dirs)


class FileSystemAssertsMixin:
    def assertIsFile(self, path: Union[PathLike, str]):
        if not Path(path).resolve().is_file():
            raise AssertionError(f"File does not exist: {path}")

    def assertIsNotFile(self, path: Union[PathLike, str]):
        if Path(path).resolve().is_file():
            raise AssertionError(f"File does exist: {path}")

    def assertIsDir(self, path: Union[PathLike, str]):
        if not Path(path).resolve().is_dir():
            raise AssertionError(f"Dir does not exist: {path}")

    def assertIsNotDir(self, path: Union[PathLike, str]):
        if Path(path).resolve().is_dir():
            raise AssertionError(f"Dir does exist: {path}")


class ConsumerProgressMixin:
    def setUp(self) -> None:
        self.send_progress_patcher = mock.patch(
            "documents.consumer.Consumer._send_progress",
        )
        self.send_progress_mock = self.send_progress_patcher.start()
        super().setUp()

    def tearDown(self) -> None:
        super().tearDown()
        self.send_progress_patcher.stop()


class DocumentConsumeDelayMixin:
    def setUp(self) -> None:
        self.consume_file_patcher = mock.patch("documents.tasks.consume_file.delay")
        self.consume_file_mock = self.consume_file_patcher.start()
        super().setUp()

    def tearDown(self) -> None:
        super().tearDown()
        self.consume_file_patcher.stop()


class TestMigrations(TransactionTestCase):
    @property
    def app(self):
        return apps.get_containing_app_config(type(self).__module__).name

    migrate_from = None
    migrate_to = None
    auto_migrate = True

    def setUp(self):
        super().setUp()

        assert (
            self.migrate_from and self.migrate_to
        ), "TestCase '{}' must define migrate_from and migrate_to     properties".format(
            type(self).__name__,
        )
        self.migrate_from = [(self.app, self.migrate_from)]
        self.migrate_to = [(self.app, self.migrate_to)]
        executor = MigrationExecutor(connection)
        old_apps = executor.loader.project_state(self.migrate_from).apps

        # Reverse to the original migration
        executor.migrate(self.migrate_from)

        self.setUpBeforeMigration(old_apps)

        self.apps = old_apps

        if self.auto_migrate:
            self.performMigration()

    def performMigration(self):
        # Run the migration to test
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()  # reload.
        executor.migrate(self.migrate_to)

        self.apps = executor.loader.project_state(self.migrate_to).apps

    def setUpBeforeMigration(self, apps):
        pass
