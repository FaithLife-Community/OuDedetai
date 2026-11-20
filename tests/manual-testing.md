# Manual testing

What the unit tests can't cover: a real Wine, a real Logos, a desktop. Copy the tables into
your test report (a pull request comment or an issue) and fill in the version tested
(`oudedetai --version`), the system (distro, desktop, X11/Wayland, GPU) and the result.

Test on a fresh install where possible (Troubleshooting → Remove everything, after a backup,
or a spare machine or user account). [docs/user-guide.md](../docs/user-guide.md) shows what
each screen should look like.

## The window

| Area | What to check | Result |
|---|---|---|
| Install | One button; Faithlife's licence shown in full; the guide ticks off each step; no Wine pop-ups (Mono, "configuration is being updated"); the bar clears at the end | |
| Sign in | First start of Logos: the browser sign-in returns to Logos | |
| Links | Logos closed: a Bible link in a browser starts Logos with the tray icon. Logos open: the link goes to it, no second tray icon | |
| Run menu | Bible, today's reading, saved layouts (needs the desktop integrations), Blank | |
| Tray | Same entries as the Run menu; Stop Logos; Quit | |
| Stop | Logos closes politely; while it syncs the dialog says so; Force ends it and leaves no Wine running (Troubleshooting → No Wine left running) | |
| While Logos runs | Repair, Back up/Restore, Wine and renderer settings, Logos's logging and Remove everything are greyed out ("Close Logos first"); Update ▸ Wine/Logos/Akousousin say "(close Logos first)" | |
| Updates | Update button counts what's available; Ou Dedetai, Wine, Akousousin and the integrations update from it | |
| Settings | Wine settings list shows all needed as Applied; Re-apply settings; Work offline (Update then refuses to go online); Releases/Prereleases | |
| Developer options | Renderer, Windows versions, Wine builds; winetricks offers missing tools; an AppImage runner without FUSE offers FUSE or unpacks itself | |
| Choose a Wine build | Newest prerelease/release; a build already on the computer isn't downloaded again; a file from the computer (bar animates until done) | |
| Media | A downloaded video resource plays (FFmpeg) | |
| Read Aloud | Akousousin voices are offered in Logos | |
| Printing | Print preview and printing to PDF (sermon templates use Georgia and Source Sans Pro) | |
| Troubleshooting | Health checks; Save a support report; Rebuild the index; Reinstall desktop integrations | |
| Image-based systems | Steam Deck / Bazzite / Silverblue: nothing is installed system-wide | |

## Terminal menu (TUI)

Run `./oudedetai-x86_64` from a terminal.

| Area | What to check | Result |
|---|---|---|
| Install | Install from the menu | |
| Run / Stop | Run Logos; Stop closes it politely | |
| Wine settings menu | Shows the current renderer and Windows versions; changing one applies without freezing the menu | |
| Updates | Releases/Prereleases, Wine builds, Update Wine, Update Akousousin, desktop integrations | |
| Offline | Work Offline on: no update checks | |

## Command line

| Command | What to check | Result |
|---|---|---|
| `--install-app -y` | Installs with the defaults, no questions | |
| `--run-installed-app` / `--stop-installed-app` | Starts Logos / closes it politely, offers to force | |
| `--update-self` | Updates the installed binary | |
| `--update-latest-appimage` | Updates Wine to the recommended build | |
| `--set-runner FILE` | Switches to a Wine AppImage or tarball; Wine Mono isn't offered on the next start | |
| `--set-update-channel prereleases` / `releases` | Follows test builds / releases | |
| `--set-renderer dxvk` | DXVK, or OpenGL where the GPU can't run it | |
| `--show-wine-config` | Lists the settings and their state | |
| `--update-wine-config` | Re-applies the settings | |
| `--set-offline on` / `--offline` | No network use | |
| `--backup` / `--restore` | | |
| `--install-desktop-integrations` | | |
| `--update-akousousin` | | |
| `--get-support` | Writes the support report | |
| `--purge` | Removes everything Ou Dedetai installed (after confirming) | |
| `--wine winecfg` | Runs a Windows program in the prefix | |
