#!/usr/bin/env bash
set -e
start_dir="$PWD"
script_dir="$(dirname "$0")"
repo_root="$(dirname "$script_dir")"
cd "$repo_root"
if ! which pyinstaller >/dev/null 2>&1 || ! which oudedetai >/dev/null; then
    # Install build deps.
    python3 -m pip install .[build]
fi
# Ensure the source in our python venv is up to date
python3 -m pip install .
# Build the installer binary
pyinstaller --clean --log-level DEBUG ou_dedetai.spec

# XXX: we may need to move this above the pyinstaller so it's included in pyinstaller's binary.
cd ou_dedetai_dbus_sender
# Compile size optimized build as directed by https://github.com/johnthagen/min-sized-rust?tab=readme-ov-file#optimize-libstd-with-build-std .
# Doing it this way rather than using the pre-compiled libstd bring s the binary size from ~312k to 73k at time of writing.
RUSTFLAGS="-Zlocation-detail=none -Zfmt-debug=none" cargo +nightly build -Z build-std=std,panic_abort -Z build-std-features="optimize_for_size" --target x86_64-unknown-linux-gnu --release
cp ou_dedetai_dbus_sender/target/x86_64-unknown-linux-gnu/release/ou_dedetai_dbus_sender dist/
cd ..

cd "$start_dir"