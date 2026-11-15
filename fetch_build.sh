#!/bin/sh
# Fetch CPCEC (Cesar Nicolas-Gonzalez, GPLv3; github.com/cpcitor/cpcec is the
# mirror) at a pinned commit, apply the patches in patches/ in order, and build
# it with SDL2. Everything lands in work/ (git-ignored): the sources, the ROM
# files that ship with CPCEC, and the `cpcec` binary. Nothing of CPCEC is kept
# in this repo, only our patches.
#
#   sh fetch_build.sh      then   work/cpcec --arnold16 ...
#
# Needs git, a C compiler and SDL2 (macOS: brew install sdl2;
# Ubuntu: apt install libsdl2-dev).
set -e
SHA=c025aab961a796b918cc99bc3e16216ea65bb5d1   # cpcitor/cpcec master, release 20260303
cd "$(dirname "$0")"
HERE=$(pwd)
mkdir -p work
cd work
if [ ! -d src/.git ]; then
    git clone -q https://github.com/cpcitor/cpcec src
fi
cd src
# always start from the clean pinned commit, so the result never depends on
# what an earlier run or a hand edit left behind
git reset -q --hard
git clean -q -fd
if [ "$(git rev-parse HEAD)" != "$SHA" ]; then
    git fetch -q origin "$SHA" 2>/dev/null || git fetch -q origin
    git checkout -q "$SHA"
fi
for p in "$HERE"/patches/*.patch; do
    if ! git apply --check "$p" 2>/dev/null; then
        echo "fetch_build.sh: $(basename "$p") does not apply to CPCEC $SHA." >&2
        echo "  If SHA was changed, the patches need rebasing onto the new commit." >&2
        exit 1
    fi
    git apply "$p"
done
# cpcec.c includes <SDL2/SDL.h>, which `sdl2-config --cflags` (it names the
# SDL2 directory itself) doesn't cover on macOS: add the parent directory.
INC=
for d in /opt/homebrew/include /usr/local/include; do
    [ -d "$d/SDL2" ] && INC="$INC -I$d"
done
# shellcheck disable=SC2046
cc -w -DSDL2 -O2 -xc cpcec.c $INC $(sdl2-config --cflags) $(sdl2-config --libs) -o cpcec
# the binary looks for its ROM files in its own directory
cp cpcec ../cpcec
for f in cpc464.rom cpc664.rom cpc6128.rom cpcados.rom cpcplus.rom; do cp "$f" ..; done
cp gpl.txt ../LICENSE.cpcec-gpl3
echo "cpcec at $(git rev-parse HEAD) with $(ls "$HERE"/patches/*.patch | wc -l | tr -d ' ') patches: $(cd .. && pwd)/cpcec"
