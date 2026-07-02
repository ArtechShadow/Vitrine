#!/bin/bash
# Build LichtFeld-Studio v0.5.3 (vendored submodule) by replicating upstream's own
# CI recipe (.github/workflows/ubuntu.yml) verbatim, in the exact CI base image
# nvidia/cuda:12.8.0-devel-ubuntu24.04. Binary -> /src/build/LichtFeld-Studio
# (host ./build, bind-mounted RO into gaussian-toolkit at /opt/gaussian-toolkit/build).
set -e
export DEBIAN_FRONTEND=noninteractive
export VCPKG_ROOT=/vcpkg
export CC=gcc-14
export CXX=g++-14
export VCPKG_BUILD_TYPE=release
export VCPKG_FORCE_SYSTEM_BINARIES=1

echo "=== [0/6] clean root-owned pollution from earlier attempt ==="
rm -rf /src/vendor/lichtfeld-studio/build && echo "vendor build dir cleaned"

echo "=== [1/6] base tools + Kitware CMake 3.30+ (CI verbatim) ==="
apt-get update -qq
apt-get install -y -qq ca-certificates gpg wget git curl unzip zip tar pkg-config
wget -qO - https://apt.kitware.com/keys/kitware-archive-latest.asc | gpg --dearmor - > /usr/share/keyrings/kitware-archive-keyring.gpg
echo 'deb [signed-by=/usr/share/keyrings/kitware-archive-keyring.gpg] https://apt.kitware.com/ubuntu/ noble main' > /etc/apt/sources.list.d/kitware.list
apt-get update -qq

echo "=== [2/6] build dependencies (CI's exact list) ==="
apt-get install -y -qq cmake gcc-14 g++-14 ccache ninja-build \
    python3 python3-dev libxinerama-dev libxcursor-dev xorg-dev libglu1-mesa-dev \
    libwayland-dev libxkbcommon-dev libegl-dev libdecor-0-dev libibus-1.0-dev libdbus-1-dev \
    libsystemd-dev libgtk-3-dev \
    nasm autoconf autoconf-archive automake libtool
update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-14 100 \
                    --slave /usr/bin/g++ g++ /usr/bin/g++-14
echo "gcc: $(gcc --version | head -1) | cmake: $(cmake --version | head -1) | nvcc: $(nvcc --version | grep release)"

echo "=== [3/6] vcpkg (fresh clone + bootstrap, CI verbatim) ==="
git clone -q https://github.com/microsoft/vcpkg.git $VCPKG_ROOT
$VCPKG_ROOT/bootstrap-vcpkg.sh -disableMetrics
cat >> $VCPKG_ROOT/triplets/x64-linux.cmake << 'EOF'
set(VCPKG_BUILD_TYPE release)
set(VCPKG_MAX_CONCURRENCY 4)
EOF

echo "=== [4/6] configure (CI flags + sm_89) ==="
cmake -B /src/build-lf -S /src/vendor/lichtfeld-studio -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CUDA_COMPILER=/usr/local/cuda/bin/nvcc \
    -DCMAKE_CUDA_ARCHITECTURES=89 \
    -DCMAKE_TOOLCHAIN_FILE=$VCPKG_ROOT/scripts/buildsystems/vcpkg.cmake \
    -DBUILD_PYTHON_STUBS=OFF \
    -DLFS_DEV_IMPORT_SOURCE_PYTHON=OFF \
    -DLFS_DEV_IMPORT_SOURCE_RESOURCES=OFF \
    -DCUDA_DEVICE_DEBUG=OFF \
    -DCMAKE_C_FLAGS="-pipe" \
    -DCMAKE_CXX_FLAGS="-pipe"

echo "=== [5/6] compile ==="
cmake --build /src/build-lf -j "$(nproc)"

echo "=== [6/6] stage binary -> /src/build ==="
BIN="$(find /src/build-lf -maxdepth 2 -type f -name 'LichtFeld-Studio' | head -1)"
[ -z "$BIN" ] && { echo "LFBUILD_FAIL: no binary"; exit 2; }
mkdir -p /src/build
cp "$BIN" /src/build/LichtFeld-Studio
chmod 755 /src/build/LichtFeld-Studio
echo "--- ldd (unresolved libs will need staging/LD_LIBRARY_PATH in the runtime container) ---"
ldd /src/build/LichtFeld-Studio | grep -E "not found" || echo "(all resolved in build env)"
ls -la /src/build/LichtFeld-Studio
"$BIN" --version 2>/dev/null || true
echo "LFBUILD_OK from=$BIN"
