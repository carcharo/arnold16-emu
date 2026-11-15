# Arnold 16 emulator: CPCEC at a pinned commit plus our patches.
#   make        fetch, patch and build        (work/cpcec)
#   make test   build, then run the tests
#   make clean  remove the build directory

.PHONY: all test clean

all:
	sh fetch_build.sh

test: all
	python3 tests/test_ping.py
	python3 tests/test_video.py

clean:
	rm -rf work
