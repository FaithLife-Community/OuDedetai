#!/usr/bin/env bash

python_ver=$(wget -qO- https://www.python.org/ftp/python/ | grep -oE '3\.12\.[0-9]+' | sort -u | tail -n1)
prefix=/opt
venv=./env

# Derived vars.
python_exec_ver="${python_ver%.*}"
python_exec_path="${prefix}/bin/python${python_exec_ver}"

# Check parent dir.
if [[ ! $(basename "$PWD") == 'LogosLinuxInstaller' ]] || [[ ! $(basename "$PWD") == 'OuDedetai' ]]; then
    echo "Error: PWD needs to be './OuDedetai'"
    echo "OuDedetai can be cloned from https://github.com/FaithLife-Community/OuDedetai.git"
    exit 1
fi

# Check for git repo.
if ! git status >/dev/null 2>&1; then
    echo "Error: $PWD is not a git repo"
    exit 1
fi

# Check for existing venv.
if [[ -d "$venv" ]]; then
    echo "Error: Folder already exists: $venv"
    exit 1
fi

# Initialize venv.
if [[ $prefix == '/opt' ]]; then
    export LD_LIBRARY_PATH=${prefix}/lib
fi
"$python_exec_path" -m venv "$venv"
echo "LD_LIBRARY_PATH=${prefix}/lib" >> "${venv}/bin/activate"
echo 'export LD_LIBRARY_PATH' >> "${venv}/bin/activate"
echo "Virtual env setup as '${venv}/'. Activate with:"
echo "source ${venv}/bin/activate"
echo
echo "Install runtime dependencies with:"
echo "pip install ."
echo
echo "To build locally install:"
echo "pip install .[build]"
