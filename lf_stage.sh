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
# Comprehensive: copy EVERY runtime .so produced/used by the build (LichtFeld's
# own liblfs_*, all vcpkg libs incl. USD, and nvImageCodec) so $ORIGIN resolves
# them next to the binary. -n = first-wins on duplicate basenames.
find "$SRC" -type f \( -name '*.so' -o -name '*.so.*' \) -exec cp -an {} "$D/" \; 2>/dev/null || true
chmod -R a+rX "$D"
echo "staged: $(find "$D" -name '*.so*' | wc -l) libs + $(ls "$D/LichtFeld-Studio")"
du -sh "$D"
