# Manual testing results

## Optarg testing

| Optargs | latest version tested | result | notes
| :--- | :--- | :---: | :--- |
| `-v/--version` | `main-20240426-09cb40d` | :+1: |
| `-F/--skip-fonts` | `4.0.0-alpha.6` | :+1: |
| `-a/--check-for-updates` | | |
| `-K/--skip-dependencies` | `4.0.0-alpha.6` | :+1: |
| `-V/--verbose` | `main-20240426-09cb40d` | :+1: |
| `-D/--debug` | `main-20240426-09cb40d` | :+1: |
| `-c/--config` | | |
| `-f/--force-root` | | |
| `-p/--custom-binary-path` | | |
| `-L/--delete-log` | `4.0.0-alpha.6` | :+1: |
| `-P/--passive` | `4.0.0-alpha.6` | :+1: |
| `--install-app` | `4.0.0-alpha.6` | :+1: |
| `--run-installed-app` | `4.0.0-alpha.6` | :+1: |
| `--run-indexing` | | |
| `--remove-library-catalog` | | |
| `--remove-index-files` | | |
| `--edit-config` | `main-20240426-09cb40d` | :-1: | gnome-text-editor symbol lookup error: /lib/x86_64-linux-gnu/libcairo.so.2: undefined symbol: FT_Get_Transform
| `--install-dependencies` | `main-20240426-09cb40d` | :+1: |
| `--backup` | | |
| `--restore` | | |
| `--update-self` | | |
| `--update-latest-appimage` | | |
| `--set-appimage` | | |
| `--get-winetricks` | | |
| `--run-winetricks` | `4.0.0-alpha.6` | :+1: |
| `--toggle-app-logging` | `4.0.0-alpha.6` | :+1: |
| `--create-shortcuts` | | |
| `--remove-install-dir` | `4.0.0-alpha.6` | :+1: |
| `--dirlink` | | |
| `--check-resources` | | |

## TUI testing

![TUI screenshot](manual-testing-tui.png)

| Option | latest version tested | result |
| :--- | :--- | :---: |
| Install [app] | `4.0.0-alpha.6` | :+1: |
| Run app | `4.0.0-alpha.6` | :+1: |
| Run indexing |||
| Remove all index files |||
| Run Winetricks | `4.0.0-alpha.6` | :+1: |
| Download/Update Winetricks |||
| Edit Config | `4.0.0-alpha.6` | :+1: |
| Back up Data |||
| Restore Data |||
| Enable/Disable [app logging] |||
| Update to Latest AppImage |||
| Set AppImage |||
| Install Dependencies |||

## GUI testing

![GUI screenshot](manual-testing-gui.png)

| Button/Action | latest version tested | result |
| :--- | :--- | :---: |
| Install [app] | `4.0.0-alpha.6` | :+1: |
| Run app | `4.0.0-alpha.6` | :+1: |
| Run indexing |||
| Remove library catalog |||
| Remove all index files |||
| Edit... [config file] | `main-20240426-09cb40d` | :-1: | Ubuntu 24.04: gnome-text-editor symbol lookup error: /lib/x86_64-linux-gnu/libcairo.so.2: undefined symbol: FT_Get_Transform
| Install [dependencies] | `main-20240426-09cb40d` | :-1: | Ubuntu 24.04: fails to prompt for password
| Backup |||
| Restore |||
| [Self-]Update |||
| Run [Update to Latest AppImage] |||
| Run [Set AppImage] |||
| Run [Winetricks] | `4.0.0-alpha.6` | :+1: |
| Download/Update [Winetricks] |||
| Enable/Disable [app logging] |||