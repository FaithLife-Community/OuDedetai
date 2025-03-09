# Contributor Documentation

## Installing/running from Source (for developers)

You can clone the repo and install the app from source. To do so, you will need to ensure a few prerequisites:
1. Install build dependencies
2. Clone this repository
3. Build/install Python 3.12 and Tcl/Tk
4. Set up a virtual environment

### Install build dependencies

e.g. for debian-based systems:
```
sudo apt-get install git build-essential gdb lcov pkg-config \
    libbz2-dev libffi-dev libgdbm-dev libgdbm-compat-dev liblzma-dev \
    libncurses5-dev libreadline6-dev libsqlite3-dev libssl-dev \
    lzma lzma-dev python3-tk tk-dev uuid-dev zlib1g-dev
```
*See Python's [Build dependencies](https://devguide.python.org/getting-started/setup-building/index.html#build-dependencies) section for further info.*

### Clone this repository
```
git clone 'https://github.com/FaithLife-Community/OuDedetai.git'
```

### Install Python 3.12 and Tcl/Tk
Your system might already include Python 3.12 built with Tcl/Tk. This will verify
the installation:
```
$ python3 --version
Python 3.12.5
$ python3 -m tkinter # should open a basic Tk window
```
If your Python version is < 3.12, then you might want to install 3.12 and tcl/tk
using your system's package manager or compile it from source using the
following guide or the script provided in `scripts/ensure-python.sh`. This is
because the app is built using 3.12 and might have errors if run with other
versions.

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
(env) OuDedetai$ python -m tkinter # verify that tkinter test window opens
(env) OuDedetai$ pip install -r .[build] # install python packages
(env) OuDedetai$ python -m ou_dedetai.main --help # run the script
```

### Building using docker

```bash
$ git clone 'https://github.com/FaithLife-Community/OuDedetai.git'
$ cd OuDedetai
# docker build -t logosinstaller .
# docker run --rm -v $(pwd):/usr/src/app logosinstaller
```

The built binary will now be in `./dist/oudedetai`.

