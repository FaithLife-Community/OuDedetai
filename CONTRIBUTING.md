# Contributor Documentation

## Installing/running from Source (for developers)

You can clone the repo and install the app from source. To do so, you will need to ensure a few prerequisites:
1. Install build dependencies
2. Clone this repository
3. Build/install Python 3.12 (or newer)
4. Set up a virtual environment

### Install build dependencies

e.g. for debian-based systems:
```
sudo apt-get install git build-essential gdb lcov pkg-config \
    libbz2-dev libffi-dev libgdbm-dev libgdbm-compat-dev liblzma-dev \
    libncurses5-dev libreadline6-dev libsqlite3-dev libssl-dev \
    lzma lzma-dev uuid-dev zlib1g-dev
```
*See Python's [Build dependencies](https://devguide.python.org/getting-started/setup-building/index.html#build-dependencies) section for further info.*

The window uses Qt (PySide6, installed by pip below). Qt's X11/Wayland plugins need a few
system libraries that some minimal installs lack, e.g. on Debian/Ubuntu:
```
sudo apt-get install libegl1 libgl1 libopengl0 libxkbcommon-x11-0 libxcb-cursor0 \
    libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0
```
(the same list CI installs in `.github/workflows/run-tests.yml`).

### Clone this repository
```
git clone 'https://github.com/FaithLife-Community/OuDedetai.git'
```

### Install Python 3.12
Your system might already include Python 3.12 or newer:
```
$ python3 --version
Python 3.12.5
```
If your Python version is < 3.12, install 3.12 using your system's package manager or
compile it from source using the following guide or `scripts/ensure-python.sh`. Release
binaries are built with 3.12.

**Install & build python 3.12 using the script:**
```
./OuDedetai/scripts/ensure-python.sh
```

**Install & build python 3.12 manually:**
```
$ ver=$(wget -qO- https://www.python.org/ftp/python/ | grep -oE '3\.12\.[0-9]+' | sort -u | tail -n1)
$ wget "https://www.python.org/ftp/python/${ver}/Python-${ver}.tar.xz"
$ tar xf Python-${ver}.tar.xz
$ cd Python-${ver}
Python-3.12$ ./configure --prefix=/opt --enable-shared
Python-3.12$ make
Python-3.12$ sudo make install
Python-3.12$ LD_LIBRARY_PATH=/opt/lib /opt/bin/python3.12 --version
Python 3.12.5
$ cd ~
```
Both methods install python into `/opt` to avoid interfering with system python installations.

### Enter the repository folder
```
$ cd OuDedetai
OuDedetai$
```

### Set up and use a virtual environment
Use the following guide or the provided script at `scripts/ensure-venv.sh` to set
up a virtual environment for running and/or building locally.

**Using the script:**
```
./scripts/ensure-venv.sh
```

**Manual setup:**

```
OuDedetai$ LD_LIBRARY_PATH=/opt/lib /opt/bin/python3.12 -m venv env # create a virtual env folder called "env" using python3.12's path
OuDedetai$ echo "LD_LIBRARY_PATH=/opt/lib" >> env/bin/activate # tell python where to find libs
OuDedetai$ echo "export LD_LIBRARY_PATH" >> env/bin/activate
OuDedetai$ source env/bin/activate # activate the env
(env) OuDedetai$ python --version # verify python version
Python 3.12.5
(env) OuDedetai$ pip install .[build] # install python packages
(env) OuDedetai$ pip install .[dev] # optional: install mypy + ruff for linting/type-checking
(env) OuDedetai$ python -m ou_dedetai.main --help # run the script
(env) OuDedetai$ DIALOG=tk python -m ou_dedetai.main # open the window
```

### Tests, lint and types
```
./scripts/run-tests.sh   # unittest; test_network.py needs the internet
ruff check
mypy ou_dedetai
```
CI runs the tests on every pull request.

### Screenshots for the docs
The pictures in `docs/images/` are drawn from stand-in data, so they never show anyone's
install. After changing the window, regenerate them:
```
QT_QPA_PLATFORM=offscreen python scripts/make-screenshots.py docs/images
```

### Building using docker

```bash
$ git clone 'https://github.com/FaithLife-Community/OuDedetai.git'
$ cd OuDedetai
# docker build -t logosinstaller .
# docker run --rm -v $(pwd):/usr/src/app logosinstaller
```

The built binary will now be in `./dist/oudedetai`.

