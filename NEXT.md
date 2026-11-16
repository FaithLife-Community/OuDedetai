# The `next` branch

`next` is a preview of the next big version of Ou Dedetai: a new, clearer window, plus the back-end
changes it needs. It's here so the team can try it and review it. **It isn't a release and isn't
meant to merge in one go.** The release plan below says what comes first.

- [Latest test build](#latest-test-build)
- [Why: what we were aiming for](#why-what-we-were-aiming-for)
- [What's new for users](#whats-new-for-users)
- [Back-end changes, and why](#back-end-changes-and-why)
- [Command line and TUI](#command-line-and-tui)
- [What depends on the oinos Wine release](#what-depends-on-the-oinos-wine-release)
- [Release plan](#release-plan)
- [How to test](#how-to-test)
- [Known gaps](#known-gaps)
- [Where the code is](#where-the-code-is)

## Latest test build

**[Branch builds of `next`](https://github.com/FaithLife-Community/OuDedetai/actions/workflows/build-branch.yml?query=branch%3Anext)**
lists them, newest first. Open the top green run and download the artifact at the bottom of the page
(`oudedetai-x86_64-…`). GitHub asks you to sign in to download artifacts. Then unzip it and run:

```
chmod +x oudedetai-x86_64-*
DIALOG=tk ./oudedetai-x86_64-*
```

From a terminal Ou Dedetai opens its TUI unless you set `DIALOG=tk`; opened from a file manager it
shows the window.

It uses your normal configuration (`~/.config/FaithLife-Community/oudedetai.json`) and install, so it
can stand in for your usual Ou Dedetai and be swapped back. **Back up first** (Troubleshooting →
Back up). Builds are made by hand from the
[Build branch workflow](https://github.com/FaithLife-Community/OuDedetai/actions/workflows/build-branch.yml)
(branch `next`); ask John if the newest commit has no build yet.

## Why: what we were aiming for

1. **Show what Ou Dedetai does.** Users and supporters couldn't see which Wine settings were applied
   or why. Now every setting is listed with its reason and whether it's applied, in the window, in
   `--show-wine-config` and in the support report.
2. **An "easy button".** One Install button, then Run / Update / Stop. Everything else sits behind
   "Settings and troubleshooting…", and developer options behind a switch.
3. **Easier support.** Health checks, one-click support report, clear errors (no error is lost in a
   background thread any more).
4. **Offline use.** Missionaries and others asked for it: a promise that Ou Dedetai won't go online.
5. **Work on image-based systems** (Steam Deck, Bazzite, Silverblue) without unlocking the system,
   and stop installing system packages people don't need.
6. **Keep existing work.** The domain code (installer, Wine, Logos, config) is reused; most changes
   are in the window. The command line and TUI stay, and get the same features.

## What's new for users

- **Simple window** (`ou_dedetai/gui_main.py`): Install, or Run ▾ / Update ▾ / Stop. The Run menu opens
  your preferred Bible, today's reading or a saved layout, or a layout named "Blank".
- **Install guide**: the install shows its ten steps in plain language as they happen, using the
  window's normal progress bar.
- **Full view**: Home (status tiles, integrations), Settings, Troubleshooting. "Open the full view when
  Ou Dedetai starts" is in Settings.
- **Settings**:
  - every Wine setting for Logos, with its reason and state, counted per group
  - Work offline
  - Ou Dedetai window options
  - developer options behind a switch: renderer, Windows versions, Wine builds (current release or
    prerelease), Wine tools (winecfg, winetricks, regedit, a Windows command prompt), run a Windows
    program
- **Troubleshooting**:
  - health checks, including ending leftover Wine processes
  - support report and logs
  - repair actions
  - backup and restore
  - **Remove everything…** (see `--purge` below)
- **Tray**: starting Logos (from its shortcut or from the window) puts Ou Dedetai in the tray. It quits
  when Logos closes unless the window is open.
  Without a display or PySide6 it falls back to the command line as before. The shortcut's right-click
  menu offers Today's reading, Stop and Ou Dedetai.
- **Links** (`logos4:`, `libronixdls:`): handed straight to Logos if it's running (as before, which is
  what sign-in uses). If it isn't, Logos starts the normal way with the link, with the tray and
  monitoring.
- **Licence**: Faithlife's licence agreement, read from the installer being installed, is shown in
  full with "I agree" before installing. Previously it was a yes/no question with a link, and the MSI
  then skipped its own licence page.
- **Desktop integrations**: offered once on KDE Plasma and on GNOME. The Plasma install offers to
  reload Plasma; GNOME asks for one log out and in.
- **Akousousin**: Update is only offered when there's a newer release. Logos can stay open.
- **Update checks** use the existing 12-hour release cache, so opening the window doesn't hit the
  servers each time. Troubleshooting → More → *Check for updates now* clears it and checks at once.
- **Look**: Faithlife's colours and type, our blue Ou Dedetai icon on the window; the Logos/Verbum
  icon only next to the product name.
- **Spanish** translation of the window (`ou_dedetai/i18n`, Qt Linguist files;
  `scripts/update-translations.py` extracts strings). The command line isn't translated; the TUI isn't
  yet.
- **Accessibility**: buttons sized by their text, keyboard-reachable, named for screen readers; nothing
  is tray-only.

## Back-end changes, and why

Each is its own commit (see `git log 14e328b..next`), so any can be dropped or reworked.

| Change | Why | Where |
|---|---|---|
| **Wine settings list** (`wine_settings.py`): each setting with its reason, which Wine needs it, and a read-back from `user.reg`/`system.reg` | Transparency; support reports; the window and `--show-wine-config` share one list | b772d70 |
| **Offline mode**: one gate in `network.py`; `--offline`, `OUDEDETAI_OFFLINE=1`, saved setting | A real promise not to connect, tested by blocking sockets | 53aea16 |
| **No system packages during install**; `OUDEDETAI_INSTALL_DEPS=1` brings the old step back; "Install dependencies" still works on request | The bundled Wine tarball installed and ran on Kubuntu 26.04, Ubuntu 26.04 GNOME and Bazzite with none of them | 47e85ed |
| **Image-based systems** (SteamOS, Bazzite, Silverblue): never install packages there | The root is read-only and replaced on update; the old SteamOS path ran `pacman -Syu` | 5483f6c |
| **Packages offered only when needed**: FUSE when an AppImage runner is chosen (or the AppImage unpacks itself if FUSE can't be installed); cabextract/7-Zip/unzip when winetricks is opened; wl-clipboard after installing the desktop integrations on Wayland if neither the system nor Akousousin has `wl-paste` (replaces #567) | Keeps AppImages and winetricks working without installing everything up front (Nathan's concern) | ae5cade, dc2ebc7, 3a420f2 |
| **Default Wine channel = prerelease (oinos)**, choice in Settings and `--set-wine-channel` | Needed until oinos is a full release; to switch back at beta 17 (see release plan) | df73d80 |
| **One-click install uses "Recommended"** | An old Wine left in the config was reused on the Deck | 5483f6c, f511bfd |
| **FFmpeg media and Logos self-update settings** applied at install and each start with an oinos Wine | Video didn't play on a fresh prefix (GStreamer path, no system plugins) | 343db43, bce9da1 |
| **Quiet prefix set-up**: wineboot runs without Wine Mono/Gecko and without a display (falls back to a normal run) | The Mono prompt and "configuration is being updated" window looked untidy | bce9da1, d239e89 |
| **Child processes get the system's libraries** (PyInstaller's `LD_LIBRARY_PATH` dropped once at start-up) | Kubuntu 26.04's `uname` failed from the binary and stopped the install | 7764f8d, 2bde6b2 |
| **`--purge` / Remove everything**: install, prefix, config, cache, logs, shortcuts, link handlers; asks about Akousousin (its own `--purge`) and the integrations; never deletes a `WINEPREFIX` override | "As if we were never there" | 0967faf, 2bf4b32 |
| **Signals and error handling** in the window: results come back through named Qt signals; a `QTimer` checks Logos; narrow `except`s; unexpected errors are shown | Taylor's review | 0967faf |

Bugs found and fixed while testing (in existing code):
- the Wine setter saved "Recommended" itself instead of the resolved choice
- the #435 snap-browser workaround set an unusable Wine
- OS detection ran `uname` and crashed on its exit code
- old icons were never replaced
- a finished Logos was left as a `<defunct>` process
- the TUI's Logos release-channel item never matched its handler

## Command line and TUI

Both use the same back end, so everything above applies to them, apart from the window itself.

- New command-line options:
  - `--show-wine-config`
  - `--offline` (this run)
  - `--set-offline on|off`
  - `--set-wine-channel stable|dev`
  - `--set-renderer dxvk|gl|vulkan|gdi`
  - `--purge` (with `-y` for scripts)
  - `--open-todays-reading`
  - `--run-installed-app [LINK]`
- New TUI items (Utilities): Show Wine Settings, Work Offline, Wine Builds, Install Desktop
  Integrations, Remove Everything (replaces Uninstall).
- Removed everywhere: **Toggle experimental media support**. With our Wine, FFmpeg is set up
  automatically, and the toggle switched back to `gdi` and GStreamer.
- `--uninstall` is unchanged.

## What depends on the oinos Wine release

- DXVK by default, Logos self-updates, FFmpeg media and the Mono/Gecko-free prefix all apply only with
  an oinos build (`wine --version` says `(oinos)`). With other Wine, Ou Dedetai behaves as before:
  `gdi` renderer, Logos updates managed by Ou Dedetai.
- The prerelease default channel and the one-click "Recommended" assume oinos is what you get.

## Release plan

1. **Beta 16: main + the small PRs that don't need oinos.** Gets everyone onto the fixed updating code
   and gives a known-good version to go back to. Candidates: #558, #554, #555, #561, #562, #563, #566,
   #564, #565.
2. **Beta 17: the oinos Wine release + #560 (DXVK).**
   - Until then oinos stays a **prerelease** on wine-appimages.
   - Ou Dedetai beta 15/16 use the release GitHub marks **Latest** (today `10.8-staging`), so they
     aren't offered oinos.
   - Publishing any full release marks it Latest automatically. If oinos is published before beta 17
     ships, untick "Set as the latest release", or
     `gh api -X PATCH repos/FaithLife-Community/wine-appimages/releases/<id> -f make_latest=false`.
3. **Switching the default runner from prerelease to release**, at beta 17:
   - publish oinos as a full release and let it become Latest
   - change `next`'s default Wine channel back to `stable` (one line in `config.py`; the choice stays
     in Settings and `--set-wine-channel`)
   - keep `10.8-staging` published as the way back
   - older Ou Dedetai (15/16) will then offer oinos through Update Wine. Logos runs and gets Wine's
     own fixes (stability, memory). The extras (DXVK, FFmpeg, self-update) need the newer Ou Dedetai,
     which sets them up by itself on the next start.
4. **Then `next`, in small PRs** on top of beta 17, in this order:
   - fixes
   - removals (system packages, media toggle)
   - foundations (settings list, offline mode, packages on demand, link handler, purge)
   - the new window
   - translations

   Release it as beta 18 or 4.1 after a round of testing.

## How to test

On a fresh install (Troubleshooting → Remove everything, or a spare machine):

1. Install with the one button: the licence window, the guide, no Wine pop-ups, a progress bar that
   clears at the end, and the Home tile "All N needed are applied".
2. **Sign in to Logos.** The link handler changed; this matters most.
3. With Logos closed, click a Bible link in a browser: Logos starts with the tray icon. With Logos
   open, a link goes to that Logos, with no second tray icon.
4. Run menu: Bible, Today's reading, Saved layouts (needs desktop integrations 0.5.1), Blank.
5. Play a downloaded video resource (FFmpeg).
6. Settings: Wine settings list, Work offline (then Update must refuse to go online), Wine builds.
7. Developer options: winetricks (offers missing tools), choose an AppImage runner on a system without
   libfuse2 (offers FUSE, or unpacks).
8. Update Akousousin: no offer when up to date; Logos can stay open.
9. Troubleshooting: health checks, support report, Remove everything (after a backup).
10. TUI (run it from a terminal) and the command-line options above.
11. Spanish: `LANGUAGE=es`.
12. Steam Deck / Bazzite: nothing installed system-wide.

## Known gaps

- Logos's installer-screen video (Windows Media Player control) is a Wine gap, being fixed on
  FaithLife-Community/wine `oinos-testing/wmp-video`. Uncached videos needing a second Play are also
  being looked at in Wine.
- "Blank" needs a saved layout called Blank: Logos has no built-in empty layout that can be opened by
  name. Quick Start layouts can't be opened by name either, so they aren't listed.
- No tray on GNOME without an AppIndicator extension (Ubuntu ships one); everything in the tray is also
  in the window.
- Snap and Flatpak builds haven't been looked at.

## Where the code is

| What | File |
|---|---|
| New window, install guide, tray | `ou_dedetai/gui_main.py` |
| Look (palette, stylesheet) | `ou_dedetai/gui_style.py` |
| Window base, the "Choose options" installer dialog, prompts, licence dialog | `ou_dedetai/gui_app.py`, `ou_dedetai/gui.py` |
| Wine settings list and read-back | `ou_dedetai/wine_settings.py` |
| Offline gate | `ou_dedetai/network.py` (`set_offline`, `_ensure_online`) |
| Purge, leftover Wine processes | `ou_dedetai/control.py` |
| Packages on demand, image-based detection, Akousousin | `ou_dedetai/system.py` |
| Quiet prefix set-up, FFmpeg/self-update settings, licence text | `ou_dedetai/wine.py` |
| Link hand-off | `ou_dedetai/logos.py` (`hand_off_link`), `ou_dedetai/installer.py` (link handler) |
| Desktop integrations bridge | `ou_dedetai/desktop_integrations.py` |
| Translations | `ou_dedetai/i18n/`, `scripts/update-translations.py` |
