**A test build of the `next` branch: not for general use.** It's for people who've offered to help test the next version of Ou Dedetai and the oinos Wine build before they become a release.

Installs on beta 16 and older don't see this build or get offered it: they follow the release marked Latest, and a prerelease never is.

### What's in it
A new qt based gui aiming to make it easier to use and clearer to understand the settings Ou Dedetai applies to Wine are shown and explained, offline mode, desktop integrations, polite Stop that waits while Logos syncs, and our oinos Wine build by default. The details, and why each change was made: [NEXT.md](https://github.com/FaithLife-Community/OuDedetai/blob/next/NEXT.md). Review and discussion: #568.

Features include:
Text to speech.
Media Playback
Printing PDFs with selectable text
etc
See https://github.com/FaithLife-Community/wine-appimages/releases?q=rc6&expanded=true


### New in dev8
- **Behind the scenes: the window's code is reorganised** after review (#568): one file per feature instead of one large file. Nothing should look or work differently, so please report anything that does.
- The "Choose options" install window no longer has a Version choice (it only ever offered Logos 10). The Release choice is unchanged, so you can still pick an older Logos release.
- `OUDEDETAI_OFFLINE` and `OUDEDETAI_NO_TRAY` are on only when set to `1`, as documented.

### New in dev7
- **The window in all the languages Logos offers**: Spanish, French, German, Portuguese, Korean, and Simplified and Traditional Chinese, following your desktop's language. These were translated with AI help: corrections from native speakers are very welcome.
- **A user guide with pictures of every screen**: [docs/user-guide.md](https://github.com/FaithLife-Community/OuDedetai/blob/next/docs/user-guide.md).
- When installing an optional package fails (FUSE, winetricks' tools, wl-clipboard), the window now says so.
- The window no longer freezes briefly on every refresh (it was checking the Wine version each time).
- Opening a saved layout from the tray no longer waits 10 seconds when Logos is already open.
- The Stop window shows its whole message, and the Settings list no longer flickers when it's rebuilt.
- Behind the scenes: a review pass so each job is done one way (downloads, running programs, registry, package offers); restarting Plasma after installing the desktop integrations now uses the system's own libraries.

### New in dev6
- **Home's buttons are Stop · Update · Run**, with Run on the right. Run indexing has moved to Troubleshooting → Repair → Rebuild the index. The simple view's link is now "Full view and settings…" and opens Home.
- **Buttons that change Logos's files or Wine settings are greyed out while Logos is open** ("Close Logos first"): repair, back up and restore, Wine and renderer settings, Logos's own logging, Remove everything. Turning Logos's logging on or off while Logos was open used to hang until Logos closed.
- **Forcing Logos to close now also ends the rest of Wine**, so nothing is left running (#412). If Logos's window has already gone but it hasn't quit, the Stop window says forcing is safe.
- Choosing Wine from a file keeps the progress bar moving until it's done.
- Removing index files no longer removes the library catalog, so rebuilding the index works (#553).
- The terminal menu's Wine settings open straight away and apply in the background (#575).

### New in dev5
- **Choosing a Wine build you already have is quick**: it's reused instead of downloaded and unpacked again (#579).
- **Choosing Wine from a file** (AppImage or tarball) now shows what it's doing, asks you to close Logos first, and applies Ou Dedetai's settings afterwards. Wine no longer offers to install Wine Mono on the next start (#576).
- **The full view opens at full size** instead of squashed with scroll bars (#573), and its Home has the **Update** button too (#572).
- The Logos version shown is read again when Logos closes, so it's right after Logos updates itself (#574).
- **Troubleshooting → Repair → Reinstall desktop integrations**, for when an OS update (seen on Bazzite and SteamOS) leaves KRunner or the copy-verse shortcut not working (#581).
- About 10 MB smaller download: Qt parts Ou Dedetai doesn't use are left out (#577).

### New in dev4
- **Logos's own logging is now on for fresh installs of test builds**, unless you've already turned it on or off yourself. Crashes during testing otherwise leave us nothing to diagnose them with (#582, #583). You can turn it off in Troubleshooting → "Logos's own logging". `Logos.log` can list the books you own, so it isn't added to the support report: send it to us separately only if you're happy to.

### How to try it
1. **Back up first**: in your current Ou Dedetai, Troubleshooting → Back up.
2. Download `oudedetai-x86_64` below, then `chmod +x oudedetai-x86_64` and run it double click.
3. If Ou Dedetai is already installed, it offers to replace the installed copy and remake the shortcuts. Your Logos install and data stay where they are.
4. From then on you're on **Prereleases** (Settings → Updates): new test builds and oinos Wine builds come through the Update button.

**There's no going back to an older version.** Switching to Releases keeps this build until a release (the next beta or later) catches up.

`oudedetai-arm` is built but hasn't been tested on any ARM machine.

### Feedback
Please report problems in #568 or in the group channel, with the log from Troubleshooting → Logs.
