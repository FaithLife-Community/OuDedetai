**A test build of the `next` branch: not for general use.** It's for people who've offered to help test the next version of Ou Dedetai and the oinos Wine build before they become a release.

Installs on beta 16 and older don't see this build or get offered it: they follow the release marked Latest, and a prerelease never is.

### What's in it
The new, clearer Ou Dedetai window (with the full view still there), the settings Ou Dedetai applies to Wine shown and explained, offline mode, desktop integrations, polite Stop that waits while Logos syncs, and the oinos Wine build by default. The details, and why each change was made: [NEXT.md](https://github.com/FaithLife-Community/OuDedetai/blob/next/NEXT.md). Review and discussion: #568.

### How to try it
1. **Back up first**: in your current Ou Dedetai, Troubleshooting → Back up.
2. Download `oudedetai-x86_64` below, then `chmod +x oudedetai-x86_64` and run it (`DIALOG=tk ./oudedetai-x86_64` from a terminal shows the window).
3. If Ou Dedetai is already installed, it offers to replace the installed copy and remake the shortcuts. Your Logos install and data stay where they are.
4. From then on you're on **Prereleases** (Settings → Updates): new test builds and oinos Wine builds come through the Update button.

**There's no going back to an older version.** Switching to Releases keeps this build until a release (the next beta or later) catches up.

`oudedetai-arm` is built but hasn't been tested on any ARM machine.

### Feedback
Please report problems in #568 or in the group channel, with the log from Troubleshooting → Logs.
