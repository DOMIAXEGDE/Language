CC ?= cc
PYTHON ?= python3
CFLAGS ?= -std=c11 -Wall -Wextra -pedantic -O2

.PHONY: all demo check clean

all: cfabric.exe

cfabric.exe: cfabric.c
	$(CC) $(CFLAGS) $< -o $@

cfabric.example.conf: cfabric.exe
	./cfabric.exe --sample-config $@

demo: cfabric.exe
	./cfabric.exe --seed 42 --canvas-count 6 --canvas-partition-count 12 --output demo-world.json
	$(PYTHON) cfabric.py demo-world.json -o demo-world.svg --show-points --labels

check: cfabric.exe
	./cfabric.exe --seed 42 --canvas-count 6 --canvas-partition-count 12 --output check-a.json
	./cfabric.exe --seed 42 --canvas-count 6 --canvas-partition-count 12 --output check-a-repeat.json
	cmp check-a.json check-a-repeat.json
	./cfabric.exe --seed 99 --canvas-count 4 --canvas-partition-count 7 --output check-b.json
	$(PYTHON) cfabric.py check-a.json --validate-only
	$(PYTHON) cfabric.py check-a.json -o check-a.svg
	$(PYTHON) clyaers.py check-a.json check-b.json --layout horizontal --collision reject --output check-composed.json
	$(PYTHON) cfabric.py check-composed.json --validate-only
	$(PYTHON) -c 'import json; d=json.load(open("check-composed.json")); assert "seed" not in d["world"]'

clean:
	rm -f cfabric.exe demo-world.json demo-world.svg check-a.json check-a-repeat.json check-a.svg check-b.json check-composed.json
