"""These functions take no arguments by default.
They can be called from CLI, GUI, or TUI.
"""

import glob
import logging
import os
import shutil
from pathlib import Path

from ou_dedetai import system
from ou_dedetai.app import App


def edit_file(config_file: str):
    system.run_command(['xdg-open', config_file])


def remove_install_dir(app: App):
    folder = Path(app.conf.install_dir)
    question = f"Delete \"{folder}\" and all its contents?"
    if not folder.is_dir():
        logging.info(f"Folder doesn't exist: {folder}")
        return
    if app.approve(question):
        shutil.rmtree(folder)
        logging.info(f"Deleted folder and all its contents: {folder}")


def remove_all_index_files(app: App):
    if not app.conf.logos_exe:
        app.exit("Cannot remove index files, Logos is not installed")
    logos_dir = os.path.dirname(app.conf.logos_exe)
    index_paths = [
        os.path.join(logos_dir, "Data", "*", "BibleIndex"),
        os.path.join(logos_dir, "Data", "*", "LibraryIndex"),
        os.path.join(logos_dir, "Data", "*", "PersonalBookIndex"),
        os.path.join(logos_dir, "Data", "*", "LibraryCatalog")
    ]
    for index_path in index_paths:
        pattern = os.path.join(index_path, "*")
        files_to_remove = glob.glob(pattern)

        for file_to_remove in files_to_remove:
            try:
                os.remove(file_to_remove)
                logging.info(f"Removed: {file_to_remove}")
            except OSError as e:
                logging.error(f"Error removing {file_to_remove}: {e}")

    app.status("Removed all LogosBible index files!", 100)


def remove_library_catalog(app: App):
    if not app.conf.logos_exe:
        app.exit("Cannot remove library catalog, Logos is not installed")
    logos_dir = os.path.dirname(app.conf.logos_exe)
    files_to_remove = glob.glob(f"{logos_dir}/Data/*/LibraryCatalog/*")
    for file_to_remove in files_to_remove:
        try:
            os.remove(file_to_remove)
            logging.info(f"Removed: {file_to_remove}")
        except OSError as e:
            logging.error(f"Error removing {file_to_remove}: {e}")
