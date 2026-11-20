[![GitHub All Releases](https://img.shields.io/github/downloads/FaithLife-Community/OuDedetai/total.svg)]()
[![Codacy Badge](https://api.codacy.com/project/badge/Grade/f730f74748c348cb9b3ff2fa1654c84b)](https://app.codacy.com/manual/FaithLife-Community/OuDedetai?utm_source=github.com&utm_medium=referral&utm_content=FaithLife-Community/OuDedetai&utm_campaign=Badge_Grade_Dashboard)
[![Automation testing](https://img.shields.io/badge/Automation-testing-sucess)](https://github.com/FaithLife-Community/LogosLinuxInstallTests) [![Installer LogosBible](https://img.shields.io/badge/Installer-LogosBible-blue)](https://www.logos.com) [![LastRelease](https://img.shields.io/github/v/release/FaithLife-Community/OuDedetai)](https://github.com/FaithLife-Community/OuDedetai/releases)

# Ou Dedetai

>Remember Jesus Christ, risen from the dead, the offspring of David, as preached in my gospel, for which I am suffering, bound with chains as a criminal. But **the word** of God **is not bound!**
>
>ἀλλʼ **ὁ λόγος** τοῦ θεοῦ **οὐ δέδεται**  

—Second Timothy 2:8–9 [ESV](https://biblia.com/bible/esv/2-timothy/2/8-9), [NA<sup>28</sup>](https://biblia.com/bible/ubs5/2-timothy/2/9)

## Manages Logos Bible Software via Wine

This repository contains a Python program for installing and maintaining [FaithLife](https://faithlife.com/)'s [Logos Bible (Verbum) Software](https://www.logos.com/) via [Wine](https://www.winehq.org/).

This program is created and maintained by the FaithLife Community and is licensed under the MIT License.

## oudedetai binary

The main program is a distributable executable binary and contains Python itself and all necessary Python packages.

When running the program, it will attempt to determine your operating system and package manager.
It will then attempt to install all needed system dependencies during the installation of Logos.
When the installation is finished, it will place two shortcuts on your computer: one will launch Logos directly; the other will launch the Control Panel.

To access the GUI version of the program, double-click the executable in your file browser or on your desktop, and then follow the prompts.

The program can also be run from source and should be run from a Python virtual environment.
See below.

## Install Guide (for users)

For an installation guide with pictures and video, see the wiki's [Install Guide](https://github.com/FaithLife-Community/OuDedetai/wiki/Install-Guide).

In Summary:
```bash
wget https://github.com/FaithLife-Community/OuDedetai/releases/latest/download/oudedetai
chmod +x ./oudedetai
DIALOG=tk ./oudedetai
```

NOTE: You can run **Ou Dedetai** using the Steam Proton Experimental binary, which often has the latest and greatest updates to make Logos run even smoother. The script should be able to find the binary automatically, unless your Steam install is located outside of your HOME directory.

If you want to install your distro's dependencies outside of the script, please see the [System Dependencies wiki page](https://github.com/FaithLife-Community/OuDedetai/wiki/System-Dependencies).

---

Soli Deo Gloria
