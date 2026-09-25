import abc
import queue
import logging
import shutil
import time
from pathlib import Path
from typing import List, Optional
from typing import Tuple
from ou_dedetai import constants
from ou_dedetai import utils
from ou_dedetai.app import App


class BackupBase(abc.ABC):
    DATA_DIRS = ['Data', 'Documents', 'Users']

    def __init__(
        self,
        app: App,
        mode: str,
    ) -> None:
        self.app = app
        self.mode = mode
        self._destination_dir: Optional[Path] = None
        self._source_dir: Optional[Path] = None
        self.data_size = 1
        self.destination_disk_used_init: Optional[int] = None
        self.q: queue.Queue[int] = queue.Queue()
        if not self.app.approve(f"Use existing backups folder \"{self.app.conf.backup_dir}\"?"):
            # Reset backup dir.
            # The app will re-prompt next time the backup_dir is accessed
            app.conf._raw.backup_dir = None
        self.backup_dir = self._ensure_backup_dir()

    def _ensure_backup_dir(self) -> Path:
        """Resolve and create the backups folder, re-prompting if it's gone.

        Handles the case where the configured location (e.g. an external disk)
        is no longer available, so the user can choose a new one instead of
        crashing.
        """
        last_failed: Optional[Path] = None
        while True:
            backup_dir = Path(self.app.conf.backup_dir).expanduser().resolve()
            try:
                backup_dir.mkdir(exist_ok=True, parents=True)
                return backup_dir
            except (FileNotFoundError, PermissionError) as e:
                m = f"Backup location not available: {backup_dir} ({e})"
                if constants.RUNMODE == 'snap':
                    m += f"\n\nTry connecting removable media:\nsnap connect {constants.BINARY_NAME}:removable-media\n"
                # Bail out rather than loop forever when we can't re-prompt or
                # the same location keeps failing.
                if self.app.conf._overrides.assume_yes or backup_dir == last_failed:
                    self.app.exit(m)
                last_failed = backup_dir
                self.app.info(m)
                # Forget the bad location so the app re-prompts on next access.
                self.app.conf._raw.backup_dir = None

    def _copy_dirs(
            self,
            src_dirs: List[str|Path] | Tuple[str|Path],
            dst_dir: Path|str,
        ) -> None:
        for src in src_dirs:
            if not isinstance(src, Path):
                src = Path(src)
            logging.debug(f"copying \"{src}\" to \"{dst_dir}/{src.name}\"")
            shutil.copytree(src, Path(dst_dir) / src.name)

    def _get_all_backups(self) -> List[str]:
        all_backups = [
            str(d) 
            for d in self.backup_dir.glob('*') 
            if d.is_dir() and d.name.startswith(self.app.conf.faithlife_product)
        ]
        all_backups.sort()
        logging.debug(all_backups)
        return all_backups

    def _get_copy_progress(self) -> Tuple[int, int]:
        """Returns (bytes_copied, percent) based on destination disk usage."""
        disk_used = self._get_dest_disk_used()
        # This should already be set by run, but in case it isn't
        if not self.destination_disk_used_init:
            self.destination_disk_used_init = disk_used

        bytes_copied = max(disk_used - self.destination_disk_used_init, 0)
        percent = min(int(bytes_copied * 100 / self.data_size), 100)
        return bytes_copied, percent

    def _get_dest_disk_used(self) -> int:
        return shutil.disk_usage(self.destination_dir).used

    def _get_dir_group_size(
        self,
        dirs: List[Path] | Tuple[Path],
    ) -> int:
        size = utils.get_folder_group_size(dirs)
        logging.debug(f"backup {size=}")
        return size

    def _get_source_subdirs(self) -> List[Path]:
        dirs = [self.source_dir / d for d in self.DATA_DIRS if (self.source_dir / d).is_dir()]
        if not dirs:
            self.app.exit(f"there are no files to {self.mode}")
        return dirs

    def _prepare_dest_dir(self) -> None:
        """Remove existing data."""
        for d in self.DATA_DIRS:
            dst = self.destination_dir / d
            if dst.is_dir():
                shutil.rmtree(dst)

    def _ensure_not_running(self) -> None:
        """Offer to stop Logos/indexing if they're running before copying data."""
        from ou_dedetai.logos import State
        self.app.logos.monitor()
        if self.app.logos.indexing_state != State.STOPPED:
            self.app.approve_or_exit(
                f"Indexing is running and must stop before {self.mode}. Stop it now?"
            )
            self.app.logos.stop_indexing()
        if self.app.logos.logos_state != State.STOPPED:
            self.app.approve_or_exit(
                f"{self.app.conf.faithlife_product} is running and must close before "
                f"{self.mode}. Close it now?"
            )
            self.app.logos.stop()

    def _confirm(self) -> None:
        """Show human-readable sizes and confirm before copying/overwriting."""
        dest_existing = utils.get_folder_group_size(
            [self.destination_dir / d for d in self.DATA_DIRS]
        )
        dest_free = shutil.disk_usage(self.destination_dir).free
        message = (
            f"About to {self.mode} {utils.format_bytes(self.data_size)} "
            f"from {self.source_dir} to {self.destination_dir}.\n"
            f"Destination currently holds {utils.format_bytes(dest_existing)} "
            f"of data, with {utils.format_bytes(dest_free)} free.\n"
            "Continue?"
        )
        self.app.approve_or_exit(message)

    def _run(self) -> None:
        self.app.status(f"Running {self.mode} from {self.source_dir} to {self.destination_dir}")
        if self.source_dir is None:
            self.app.exit("source directory not set")
        elif self.destination_dir is None:
            self.app.exit("destination directory not set")
        self._ensure_not_running()
        src_dirs = self._get_source_subdirs()

        self.data_size = self._get_dir_group_size(src_dirs)
        self._verify_disk_space()
        self._confirm()
        self._prepare_dest_dir()
        # Capture the baseline after clearing the destination so copy progress
        # is measured against what's actually written during this run.
        self.destination_disk_used_init = self._get_dest_disk_used()
        t = self.app.start_thread(self._copy_dirs, src_dirs, self.destination_dir)
        try:
            while t.is_alive():
                bytes_copied, percent = self._get_copy_progress()
                self.app.status(
                    f"Copying… {percent}% "
                    f"({utils.format_bytes(bytes_copied)} / "
                    f"{utils.format_bytes(self.data_size)})",
                    percent,
                )
                time.sleep(0.5)
            print()
        except KeyboardInterrupt:
            print()
            self.app.exit("user cancelled with Ctrl+C.")
        t.join()
        m = f"Finished {self.mode}. {utils.format_bytes(self.data_size)} copied."
        self.app.status(m)

    def _verify_disk_space(self) -> None:
        if not utils.enough_disk_space(self.destination_dir, self.data_size):
            try:
                self.destination_dir.rmdir()
            except OSError:  # folder not empty
                logging.error(f"Tried to remove non-empty folder: {self.destination_dir}")
            self.app.exit(f"not enough free disk space for {self.mode}.")
        logging.debug(f"Sufficient space verified on {self.destination_dir} disk.")

    @property
    def source_dir(self) -> Path:
        if not self._source_dir:
            self._source_dir = self._get_source_dir()
        return self._source_dir

    @abc.abstractmethod
    def _get_source_dir(self) -> Path:
        """Source path. Differs depending on backup/restore"""
        raise NotImplementedError

    @property
    def destination_dir(self) -> Path:
        if not self._destination_dir:
            self._destination_dir = self._get_destination_dir()
        return self._destination_dir

    @abc.abstractmethod
    def _get_destination_dir(self) -> Path:
        """Destination path. Differs depending on backup/restore"""
        raise NotImplementedError


class BackupTask(BackupBase):
    def __init__(self, app: App) -> None:
        super().__init__(app, 'backup')
        self.description = 'Use'

    def run(self) -> None:
        """Run the backup task."""
        self._run()

    def _get_source_dir(self) -> Path:
        if self.app.conf._logos_appdata_dir is None:
            self.app.exit("Cannot backup when product is not installed.")
        return Path(self.app.conf._logos_appdata_dir).expanduser().resolve()

    def _get_destination_dir(self) -> Path:
        """Destination path. Differs depending on backup/restore"""
        timestamp = utils.get_timestamp().replace('-', '')
        name = f"{self.app.conf.faithlife_product}-{timestamp}"
        destination_dir = self.backup_dir / name
        logging.debug(f"Backup directory path: {destination_dir}.")

        # Check for existing backup.
        try:
            destination_dir.mkdir()
        except FileExistsError:
            # This shouldn't happen, there is a timestamp in the backup_dir name
            logging.warning(f"Backup already exists at: {destination_dir}.")
        return destination_dir


class RestoreTask(BackupBase):
    def __init__(self, app: App) -> None:
        super().__init__(app, 'restore')

    def run(self) -> None:
        """Run the restore task."""
        self._run()

    def _get_destination_dir(self) -> Path:
        if self.app.conf._logos_appdata_dir is None:
            self.app.exit("Cannot backup when product is not installed.")
        return Path(self.app.conf._logos_appdata_dir).expanduser().resolve()

    def _get_source_dir(self) -> Path:
        all_backups = self._get_all_backups()
        latest = all_backups.pop(-1)

        # Offer to restore the most recent backup.
        options = [latest, *all_backups]
        src_dir = self.app.ask("Choose backup folder to restore: ", options)

        return Path(src_dir)


def backup(app: App) -> None:
    backup = BackupTask(app)
    backup.run()


def restore(app: App) -> None:
    restore = RestoreTask(app)
    restore.run()
