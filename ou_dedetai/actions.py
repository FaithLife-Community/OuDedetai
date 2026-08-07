import curses
import logging

from ou_dedetai import system, gui_app, tui_app, cli
from ou_dedetai.config import EphemeralConfiguration


def run_control_panel(ephemeral_config: EphemeralConfiguration):
    dialog = ephemeral_config.dialog or system.get_dialog()
    logging.info(f"Using DIALOG: {dialog}")
    if dialog == 'tk':
        gui_app.start_gui_app(ephemeral_config)
    else:
        try:
            curses.wrapper(tui_app.control_panel_app, ephemeral_config)
        except KeyboardInterrupt:
            raise
        except SystemExit:
            logging.info("Caught SystemExit, exiting gracefully…")
            raise
        except curses.error as e:
            logging.error(f"Curses error in run_control_panel(): {e}")
            raise e
        except Exception as e:
            logging.error(f"An error occurred in run_control_panel(): {e}")
            raise e


def install_app(ephemeral_config: EphemeralConfiguration):
    dialog = ephemeral_config.dialog or system.get_dialog()
    logging.info(f"Using DIALOG: {dialog}")
    if dialog == 'tk':
        gui_app.start_gui_app(ephemeral_config, install_only=True)
    else:
        cli.CLI(ephemeral_config).install_app()
