#!/bin/sh
# Regenerate patches/0002-arnold16.patch from the edited sources in work/src.
# The patch must hold only the Arnold 16 changes, so this compares the edited
# cpcec.c and cpcec-a16.h with a fresh copy of the pinned CPCEC commit that has
# patch 0001 applied. work/src itself is not changed.
#
#   sh tools/mkpatch.sh            write patches/0002-arnold16.patch
#   sh tools/mkpatch.sh FILE       write the patch to FILE instead, quietly
set -e
cd "$(dirname "$0")/.."
HERE=$(pwd)
[ -f work/src/cpcec-a16.h ] || { echo "mkpatch.sh: no work/src: run make first" >&2; exit 1; }
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
git clone -q work/src "$T/s"
cd "$T/s"
git apply "$HERE/patches/0001-cpcbuild-headless.patch"
git add -A
git -c user.email=mkpatch@localhost -c user.name=mkpatch commit -qm "patch 0001"
cp "$HERE/work/src/cpcec.c" "$HERE/work/src/cpcec-a16.h" .
git add -A
if [ -n "$1" ]; then
    case "$1" in /*) OUT=$1 ;; *) OUT=$HERE/$1 ;; esac
    git diff --cached > "$OUT"
else
    git diff --cached > "$HERE/patches/0002-arnold16.patch"
    git diff --cached --stat
fi
