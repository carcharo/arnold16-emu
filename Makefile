# Arnold 16 emulator: CPCEC at a pinned commit plus our patches.
#   make        fetch, patch and build        (work/cpcec)
#   make test   build, then run the tests
#   make demo   build, then run the demo in a window
#   make clean  remove the build directory

.PHONY: all test demo clean

all:
	sh fetch_build.sh

test: all
	python3 tests/test_ping.py
	python3 tests/test_boot.py
	python3 tests/test_video.py
	python3 tests/test_demo.py

demo: all
	work/cpcec --arnold16 --a16-serial-in work/demo.a16 -m2 work/demo.dsk

clean:
	rm -rf work
