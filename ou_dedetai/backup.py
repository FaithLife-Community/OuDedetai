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
        self.backup_dir = Path(self.app.conf.backup_dir).expanduser().resolve()
        try:
            self.backup_dir.mkdir(exist_ok=True, parents=True)
        except PermissionError:
            m = f"folder not accessible: {self.backup_dir}"
            if constants.RUNMODE == 'snap':
                m += f"{m}\n\nTry connecting removable media:\nsnap connect {constants.BINARY_NAME}:removable-media\n"
            self.app.exit(m)

    def _copy_dirs(
            self,
            src_dirs: List[str|Path] | Tuple[str|Path],
            dst_dir: Path|str,
        ) -> None:
        # logging.debug("starting _copy_dirs")
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

    def _get_copy_percentage(self) -> int:
        disk_used = self._get_dest_disk_used()
        # This should already be set by run, but in case it isn't
        if not self.destination_disk_used_init:
            self.destination_disk_used_init = disk_used

        delta = disk_used - self.destination_disk_used_init
        percent = int(delta * 100 / self.data_size)
        # logging.debug(f"{percent=}")
        return percent

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

    def _run(self) -> None:
        self.app.status(f"Running {self.mode} from {self.source_dir} to {self.destination_dir}") 
        if self.source_dir is None:
            self.app.exit("source directory not set")
        elif self.destination_dir is None:
            self.app.exit("destination directory not set")
        src_dirs = self._get_source_subdirs()

        self.data_size = self._get_dir_group_size(src_dirs)
        self._prepare_dest_dir()
        self.destination_disk_used_init = self._get_dest_disk_used()
        self._verify_disk_space()
        # logging.debug("starting data copy thread")
        t = self.app.start_thread(self._copy_dirs, src_dirs, self.destination_dir)
        try:
            while t.is_alive():
                self.app.status("copying…", self._get_copy_percentage())
                time.sleep(0.5)
            print()
        except KeyboardInterrupt:
            print()
            self.app.exit("user cancelled with Ctrl+C.")
        t.join()
        # logging.debug("finished data copy thread")
        m = f"Finished {self.mode}. {self.data_size} bytes copied."
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
