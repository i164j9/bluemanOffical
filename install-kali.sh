#!/usr/bin/env bash

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: ./install-kali.sh [--prefix PREFIX] [--run-tests] [--refresh-autotools] [--clean-build] [--help]

Install Blueman from the current checkout on Kali or another Debian-family
system.

Options:
    --prefix PREFIX       Install prefix passed to configure (default: /usr/local)
    --run-tests           Run pytest after building and before installation
    --refresh-autotools   Rebuild configure/Makefile.in files with ./autogen.sh
    --clean-build         Run make distclean or make clean in the staged tree before rebuilding
    --help                Show this help text
EOF
}

prefix="/usr/local"
run_tests=false
refresh_autotools=false
clean_build=false
stage_root=""
python_install_dir=""

cleanup_stage() {
    local exit_code=$?

    if [[ -n "$stage_root" ]]; then
        if (( exit_code == 0 )); then
            rm -rf "$stage_root"
        else
            echo "Build directory preserved at $stage_root" >&2
        fi
    fi

    exit "$exit_code"
}

trap cleanup_stage EXIT

while (($# > 0)); do
    case "$1" in
        --prefix)
            shift
            if (($# == 0)); then
                echo "Missing value for --prefix" >&2
                exit 1
            fi
            prefix="$1"
            ;;
        --run-tests)
            run_tests=true
            ;;
        --refresh-autotools)
            refresh_autotools=true
            ;;
        --clean-build)
            clean_build=true
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
    shift
done

if [[ ! -r /etc/os-release ]]; then
    echo "Cannot determine the current distribution: /etc/os-release is missing." >&2
    exit 1
fi

. /etc/os-release

if [[ "${ID:-}" != "kali" && " ${ID_LIKE:-} " != *" debian "* ]]; then
    echo "This installer is intended for Kali or another Debian-family system." >&2
    exit 1
fi

sudo_cmd=()
if ((EUID != 0)); then
    if command -v sudo >/dev/null 2>&1; then
        sudo_cmd=(sudo)
    else
        echo "Please run this script as root or install sudo." >&2
        exit 1
    fi
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python_install_dir="$(python3 - "$prefix" <<'PY'
import pathlib
import site
import sys

prefix = pathlib.Path(sys.argv[1]).resolve()
candidates: list[tuple[int, int, int, int, pathlib.Path]] = []

for raw in site.getsitepackages():
    path = pathlib.Path(raw).resolve()
    try:
        relative = path.relative_to(prefix)
    except ValueError:
        continue

    under_lib = 0 if relative.parts and relative.parts[0] == "lib" else 1
    prefers_dist_packages = 0 if path.name == "dist-packages" else 1
    prefers_versionless = 0 if "python3/dist-packages" in path.as_posix() else 1
    candidates.append((under_lib, prefers_dist_packages, prefers_versionless, len(relative.parts), path))

if candidates:
    print(min(candidates)[-1])
PY
)"

if [[ -n "$python_install_dir" ]]; then
    echo "Using Python install directory override: $python_install_dir"
fi

packages=(
    autoconf
    automake
    autopoint
    bluez
    bluez-obexd
    build-essential
    cython3
    gettext
    gir1.2-gtk-3.0
    gir1.2-nm-1.0
    iproute2
    libbluetooth-dev
    libdbus-1-dev
    libglib2.0-bin
    libglib2.0-dev
    libnm-dev
    libpulse-dev
    libpulse-mainloop-glib0
    libtool
    pkg-config
    python-gi-dev
    python3-cairo
    python3-dbus
    python3-dev
    python3-gi
)

if [[ "$run_tests" == true ]]; then
    packages+=(python3-dbusmock python3-pytest)
fi

echo "Installing Blueman dependencies with apt..."
"${sudo_cmd[@]}" apt-get update
"${sudo_cmd[@]}" apt-get install -y --no-install-recommends "${packages[@]}"

cd "$repo_root"

stage_root="$(mktemp -d "${TMPDIR:-/tmp}/blueman-install.XXXXXX")"
stage_src="$stage_root/src"
mkdir -p "$stage_src"

echo "Preparing isolated build directory at $stage_src..."
tar -C "$repo_root" \
    --exclude=.git \
    --exclude=.vscode \
    --exclude=.pytest_cache \
    -cf - . | tar -C "$stage_src" -xf -

cd "$stage_src"

if [[ "$clean_build" == true ]]; then
    if [[ -f Makefile ]]; then
        echo "Cleaning copied build artifacts in staged source tree..."
        if ! make distclean; then
            echo "make distclean failed; retrying with make clean..."
            make clean
        fi
    else
        echo "No Makefile found in staged source tree; skipping make-based clean step."
    fi
fi

configure_args=(--enable-maintainer-mode "--prefix=$prefix")

if [[ "$refresh_autotools" == true || ! -x ./configure ]]; then
    echo "Bootstrapping autotools build files..."
    CYTHONEXEC=cython3 ./autogen.sh "${configure_args[@]}"
else
    echo "Configuring Blueman..."
    CYTHONEXEC=cython3 ./configure "${configure_args[@]}"
fi

echo "Building Blueman..."
make -j"$(nproc)"

if [[ "$run_tests" == true ]]; then
    echo "Running test suite..."
    python3 -m pytest -q
fi

echo "Installing Blueman into $prefix..."
install_args=()
if [[ -n "$python_install_dir" ]]; then
    install_args+=("pythondir=$python_install_dir" "pyexecdir=$python_install_dir")
fi
"${sudo_cmd[@]}" make install "${install_args[@]}"

schema_dir="$prefix/share/glib-2.0/schemas"
if command -v glib-compile-schemas >/dev/null 2>&1 && [[ -d "$schema_dir" ]]; then
    echo "Refreshing installed GSettings schemas..."
    "${sudo_cmd[@]}" glib-compile-schemas "$schema_dir"
fi

echo "Installation complete."