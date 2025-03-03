import queue
import logging
import shutil
import time
from pathlib import Path
from typing import List
from typing import Tuple
from ou_dedetai import constants
from ou_dedetai import utils
from ou_dedetai.app import App


class BackupBase:
    DATA_DIRS = ['Data', 'Documents', 'Users']

    def __init__(self, app: App) -> None:
        self.app = app
        self.mode = None
        self.source_dir = None
        self.data_size = None
        self.destination_dir = None
        self.destination_disk_used_init = None
        self.q: queue.Queue[int] = queue.Queue()
        if not self.app.approve(f"Use existing backups folder \"{self.app.conf.backup_dir}\"?"): # noqa: E501
            # Reset backup dir.
            # The app will re-prompt next time the backup_dir is accessed
            app.conf._raw.backup_dir = None
        self.backup_dir = Path(self.app.conf.backup_dir).expanduser().resolve()
        try:
            self.backup_dir.mkdir(exist_ok=True, parents=True)
        except PermissionError:
            m = f"folder not accessible: {self.backup_dir}"
            if constants.RUNMODE == 'snap':
                m += f"{m}\n\nTry connecting removable media:\nsnap connect {constants.BINARY_NAME}:removable-media\n"  # noqa: E501
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
        all_backups = [str(d) for d in self.backup_dir.glob('*') if d.is_dir() and d.name.startswith(self.app.conf.faithlife_product)]  # noqa: E501
        all_backups.sort()
        logging.debug(all_backups)
        return all_backups

    def _get_copy_percentage(self) -> int:
        delta = self._get_dest_disk_used() - self.destination_disk_used_init
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
        dirs = [self.source_dir / d for d in self.DATA_DIRS if (self.source_dir / d).is_dir()]  # noqa: E501
        if not dirs:
            self.app.exit(f"there are no files to {self.mode}")
        return dirs

    def _prepare_dest_dir(self) -> None:
        """Remove existing data."""
        for d in self.DATA_DIRS:
            dst = Path(self.destination_dir) / d
            if dst.is_dir():
                shutil.rmtree(dst)

    def _run(self) -> None:
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
                self.app.status("copying…\r", self._get_copy_percentage())
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
                logging.error(f"Tried to remove non-empty folder: {self.destination_dir}")  # noqa: E501
            self.app.exit(f"not enough free disk space for {self.mode}.")
        logging.debug(f"Sufficient space verified on {self.destination_dir} disk.")


class BackupTask(BackupBase):
    def __init__(self, app: App) -> None:
        super().__init__(app)
        self.mode = 'backup'
        self.description = 'Use'
        self.source_dir = Path(self.app.conf._logos_appdata_dir).expanduser().resolve()

    def run(self) -> None:
        """Run the backup task."""
        self._set_dest_dir()
        self.app.status(f"Backing up data to: {self.destination_dir}")
        self._run()

    def _set_dest_dir(self) -> None:
        timestamp = utils.get_timestamp().replace('-', '')
        name = f"{self.app.conf.faithlife_product}-{timestamp}"
        self.destination_dir = self.backup_dir / name
        logging.debug(f"Backup directory path: {self.destination_dir}.")

        # Check for existing backup.
        try:
            self.destination_dir.mkdir()
        except FileExistsError:
            # This shouldn't happen, there is a timestamp in the backup_dir name
            self.app.exit(f"backup already exists at: {self.destination_dir}.")


class RestoreTask(BackupBase):
    def __init__(self, app: App) -> None:
        super().__init__(app)
        self.mode = 'restore'

    def run(self) -> None:
        """Run the restore task."""
        if self.source_dir is None:
            self._set_source_dir()
        self._set_dest_dir()

        self.app.status(f"Restoring backup from: {self.source_dir}")
        self._run()

    def set_source_dir(self, src_dir: Path | str) -> None:
        """Explicitly set dir path to restore from"""
        self._set_source_dir(src_dir)

    def _set_dest_dir(self) -> None:
        # TODO: Use faithlife_product here? Ensure file exists?
        if not self.app.conf.logos_exe:
            self.app.exit("Logos is not installed.")
        self.destination_dir = Path(self.app.conf.logos_exe).parent

    def _set_source_dir(self, src_dir: Path = None) -> None:
        if src_dir is None:
            all_backups = self._get_all_backups()
            latest = all_backups.pop(-1)

            # Offer to restore the most recent backup.
            options = [latest, *all_backups]
            src_dir = self.app.ask("Choose backup folder to restore: ", options)

        if not isinstance(src_dir, Path):
            src_dir = Path(src_dir)
        self.source_dir = src_dir


def backup(app: App) -> None:
    backup = BackupTask(app)
    backup.run()


def restore(app: App) -> None:
    restore = RestoreTask(app)
    restore.run()
