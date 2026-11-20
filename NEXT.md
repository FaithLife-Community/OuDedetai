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

**[Prereleases on the Releases page](https://github.com/FaithLife-Community/OuDedetai/releases)**: the
newest one titled "next test build" (`v4.0.0-beta.17.devN`). No GitHub sign-in needed. Download
`oudedetai-x86_64` (`oudedetai-arm` is built but untested), then:

```
chmod +x oudedetai-x86_64
./oudedetai-x86_64
```

- If Ou Dedetai is already installed, it offers to replace the installed copy and remake the
  shortcuts. It uses your normal configuration (`~/.config/FaithLife-Community/oudedetai.json`) and
  install. **Back up first** (Troubleshooting → Back up).
- From then on it follows **Prereleases** (Settings → Updates): new test builds and oinos Wine builds
  come through the Update button.
- Switching to **Releases** doesn't take you back: you stay on the test build until a release
  (beta 17 or later) catches up.
- Installs on beta 16 and older never see these builds: they follow the release marked Latest (or
  test-builds on the dev channel), and a prerelease is never Latest.

From a terminal Ou Dedetai opens its TUI unless you set `DIALOG=tk`; opened from a file manager it
shows the window. Between prereleases, every commit can also be built with the
[Build branch workflow](https://github.com/FaithLife-Community/OuDedetai/actions/workflows/build-branch.yml?query=branch%3Anext)
(GitHub sign-in needed to download).

## Why: what we were aiming for

1. **Show what Ou Dedetai does.** Users and supporters couldn't see which Wine settings were applied
   or why. Now every setting is listed with its reason and whether it's applied, in the window, in
   `--show-wine-config` and in the support report.
2. **An "easy button".** One Install button, then Run / Update / Stop. Everything else sits behind
   "Full view and settings…", and developer options behind a switch.
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
- **Updates: Releases / Prereleases** (Settings, TUI *Updates*, `--set-update-channel`): one choice for
  Ou Dedetai and Wine. Prereleases follows OuDedetai prereleases (`next` test builds, numbered
  `4.0.0-beta.17.devN`) and the oinos Wine prereleases; Releases follows Latest. Nothing ever goes back:
  switching to Releases waits until a release catches up. A development build follows Prereleases
  until the user chooses. (`main`'s dev channel, test-builds, is untouched.)
- **Running a newer build from elsewhere** (e.g. a downloaded test build from Downloads) offers to put it
  in place of the installed copy and remake the shortcuts. An older one is never put in place.
- **Choose a Wine build** (Troubleshooting → More) offers the newest prerelease and newest release
  bundles by name, marks the one in use, and still offers a file. Picking a bundle also sets the Wine
  channel, so later updates follow it. An installed tarball is now compared with the channel's tarball
  (it was compared with the AppImage release, so new rcs weren't offered).
- **Stop closes Logos politely** (window, tray, TUI, `--stop-installed-app`): Ou Dedetai asks Logos to
  close as its close button does (Wine's `taskkill` without `/F`) and waits. While Logos looks busy
  (CPU or disk writing: probably syncing or saving) it keeps waiting and says so; if it sits idle it
  may be asking something. Forcing it (the old `kill -9`) is offered with a warning, never done
  unattended. `LogosManager.stop()` itself is unchanged and still used internally.
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
- **Desktop integrations**: a newer release shows in the Update menu and on the Settings card's
  button (GUI), as a status line plus *Update Desktop Integrations* (TUI), and
  `--install-desktop-integrations` installs the latest (CLI). The installed version is read from
  `~/.local/share/logos-plasma/VERSION` (v0.5.1+; older installs count as older).
- **Update checks** use the existing 12-hour release cache, so opening the window doesn't hit the
  servers each time. Troubleshooting → More → *Check for updates now* clears it and checks at once.
- **Look**: Faithlife's colours and type, our blue Ou Dedetai icon on the window; the Logos/Verbum
  icon only next to the product name.
- **Translations** of the window into the languages Logos offers: Spanish, French, German,
  Portuguese, Korean, and Simplified and Traditional Chinese (`ou_dedetai/i18n`, Qt Linguist files;
  `scripts/update-translations.py` extracts strings). It follows the desktop's language; Chinese
  outside mainland China and Taiwan picks by script. AI-translated: corrections from native speakers
  welcome. Messages from the install steps and the command line and TUI stay in English.
- **Docs**: [docs/user-guide.md](docs/user-guide.md) with screenshots of every screen
  (`scripts/make-screenshots.py`).
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
| **Development builds follow Prereleases (oinos)**, choice in Settings → Updates and `--set-update-channel` | Testers get oinos and new test builds; a release build keeps Releases (see release plan) | df73d80 |
| **One-click install uses "Recommended"** | An old Wine left in the config was reused on the Deck | 5483f6c, f511bfd |
| **FFmpeg media and Logos self-update settings** applied at install and each start with an oinos Wine | Video didn't play on a fresh prefix (GStreamer path, no system plugins) | 343db43, bce9da1 |
| **Quiet prefix set-up**: wineboot runs without Wine Mono/Gecko and without a display (falls back to a normal run) | The Mono prompt and "configuration is being updated" window looked untidy | bce9da1, d239e89 |
| **Child processes get the system's libraries** (PyInstaller's `LD_LIBRARY_PATH` dropped once at start-up) | Kubuntu 26.04's `uname` failed from the binary and stopped the install | 7764f8d, 2bde6b2 |
| **`--purge` / Remove everything**: install, prefix, config, cache, logs, shortcuts, link handlers; asks about Akousousin (its own `--purge`) and the integrations; never deletes a `WINEPREFIX` override | "As if we were never there" | 0967faf, 2bf4b32 |
| **Logos logging on during the beta**: a fresh install on a beta/dev build turns on Logos's own logging unless the user has already chosen; release builds don't | Crash dumps only show that a .NET exception went unhandled (#582); `Logos.log` says which one. Logos.log can list the user's books, so the support zip still leaves it out | `ensure_beta_product_logging` |
| **Choosing a Wine build already on the computer** reuses it instead of downloading and unpacking it again | Switching between builds was slow for no reason (#579) | `wine._unpacked_wine_build` |
| **Wine from a file** says what it's doing, waits for Logos to be closed, applies Ou Dedetai's settings afterwards, and updates the prefix without the Wine Mono offer for AppImages too | The window looked stuck, and Wine offered Mono on the next start (#576) | `installer.use_wine_file`, `utils.set_appimage_symlink` |
| **Full view opens at full size**; Update menu on Home; Logos version re-read when Logos closes | A start-up resize meant for the simple view shrank the full view (#573); updates weren't visible from Home (#572); the version shown was stale after Logos updated itself (#574) | `_fit_full`, `h_update` |
| **Reinstall desktop integrations** under Troubleshooting → Repair | An OS update on Bazzite/SteamOS left KRunner and the copy-verse shortcut not working until reinstalled (#581) | `t_integrations` |
| **Home's buttons are Stop · Update · Run**, the simple view's Run · Update · Stop reversed because the row is right-aligned; Run indexing moved to Troubleshooting → Repair → Rebuild the index (same action, now greyed out while Logos runs); the simple view's link "Full view and settings…" opens Home | Update to the right of Run looked wrong; indexing is a repair step; the link jumped straight to Settings | `_build_home`, `t_reindex` |
| **Choosing Wine from a file animates the progress bar** until it's done | It said "Setting up…" with no bar, so it looked finished while the AppImage was still being copied | `set_appimage` |
| **Greyed out while Logos runs** ("Close Logos first"): Re-apply settings, renderer and Windows-version Apply, winetricks, Logos's own logging, Rebuild the index, Remove the library catalog / index files, Reinstall ICU, Back up, Restore, Choose a Wine build, Remove everything; Update ▸ Wine, Logos and Akousousin say "(close Logos first)" | They change Logos's files or its prefix; the logging switch waited for Wine to exit, so with Logos open it hung until Logos closed; backups taken while Logos writes can be inconsistent (#197) | `closed_only`, `while_closed` |
| **Force also ends the rest of Wine** (`wineserver -k` after killing Logos), in the window, tray and command line; the Stop dialog says forcing is safe once Logos's window has gone (the shutdown hang); "Tidy up before Logos starts" describes what Ou Dedetai really does | Forcing used to leave wineserver and helpers running (#412). Ou Dedetai can't yet tell a Logos stuck shutting down from one asking a question (Wine's taskkill also counts hidden windows), so it never forces on its own | `LogosManager.force_close` |
| **Smaller binary**: unused Qt parts (Quick/QML via the virtual keyboard plugin, Pdf, extra image formats and platforms, non-base translations) left out | About 10 MB smaller (#577) | `ou_dedetai.spec` |
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

1. **Beta 16 (released 17 Nov)**: main with the new updating code; it can tell Latest from prereleases.
2. **`next` test builds as OuDedetai prereleases**, `v4.0.0-beta.17.devN`: newer than beta 16, older
   than beta 17, never Latest, so no current install sees them. Testers opt in by downloading one.
   The first ones are made by hand (draft prerelease, published by a maintainer); a PR adds a
   workflow for it (`build-next-prerelease.yml`), for the team to review.
3. **oinos Wine stays a prerelease on wine-appimages until agreed.** Beta 16's default Wine channel
   follows the **Latest** tarball there, so marking an oinos build Latest changes every beta 16
   user's recommended Wine. If oinos is published as a full release early, untick "Set as the latest
   release", or `gh api -X PATCH repos/FaithLife-Community/wine-appimages/releases/<id> -f make_latest=false`.
4. **When oinos is released**: publish it as Latest, keep `10.8-staging` published as the way back,
   and release `next`'s work (in the PRs the team prefers) as beta 17 or 4.0.0. Older Ou Dedetai then
   offers oinos through Update Wine; the extras (DXVK, FFmpeg, self-update) need the newer Ou Dedetai,
   which sets them up on its next start.
5. `main`'s dev channel still follows test-builds. `next` points Prereleases at OuDedetai prereleases;
   whether `main` does the same is the team's call when `next` is merged.

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
8. Update Akousousin: no offer when up to date; greyed out while Logos runs (it registers in the prefix).
9. Troubleshooting: health checks, support report, Remove everything (after a backup). Stop: polite
   close, Force leaves no Wine running; buttons that change Logos's files are greyed out while it runs.
10. TUI (run it from a terminal) and the command-line options above.
11. Languages: `LANG=fr_FR.UTF-8` (or de_DE, es_ES, pt_BR, ko_KR, zh_CN, zh_TW, zh_HK).
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
