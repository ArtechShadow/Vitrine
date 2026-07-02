#!/bin/bash
# Stage LichtFeld's runtime .so tree next to the executable in /src/build so the
# binary's RUNPATH ($ORIGIN) resolves them inside the gaussian-toolkit container.
# Run as root (build-lf artifacts are root-owned).
set -e
SRC=/src/build-lf
D=/src/build
# Clear CONTENTS but keep the directory inode — it is bind-mounted into the
# running gaussian-toolkit container, and rm -rf'ing it orphans that mount.
mkdir -p "$D"
find "$D" -mindepth 1 -delete 2>/dev/null || true
cp -a "$SRC/LichtFeld-Studio" "$D/"
# LichtFeld's own shared libs (live at build-lf root)
cp -a "$SRC"/liblfs_*.so "$D/" 2>/dev/null || true
# vcpkg release runtime libs (USD, nvimgcodec, etc.)
find "$SRC/vcpkg_installed/x64-linux/lib" -maxdepth 1 -name '*.so*' -exec cp -a {} "$D/" \; 2>/dev/null || true
find "$SRC/vcpkg_installed/x64-linux/bin" -maxdepth 1 -name '*.so*' -exec cp -a {} "$D/" \; 2>/dev/null || true
# any other .so the build produced under Build/lib
find "$SRC" -maxdepth 3 -path '*/Build/lib/*.so*' -exec cp -a {} "$D/" \; 2>/dev/null || true
chmod -R a+rX "$D"
echo "staged: $(find "$D" -name '*.so*' | wc -l) libs + $(ls "$D/LichtFeld-Studio")"
du -sh "$D"
