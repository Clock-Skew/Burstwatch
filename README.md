# burstwatch

Passive RF burst analysis and device-discovery workflow tooling for owned or authorized captures.

`burstwatch` is file-first on purpose. It does not control the SDR, it does not transmit, and it does not try to decode private traffic. Its job is to turn saved IQ or WAV captures into passive RF metadata you can review, baseline, diff, and feed into later dashboards.

## Recommended model

- Use `standard` for implementation work.
- Use `deep` for classifier tuning or RF edge-case analysis.
- Use `quick` for small follow-up edits and smoke checks.

## What it does

- `analyze`: classify burst shapes inside one capture
- `scan`: cluster bursts into passive emitter candidates
- `fingerprint`: derive reusable passive fingerprints from scan candidates
- `baseline`: learn normal emitter profiles from prior scans
- `watch`: compare a fresh scan against a saved baseline

Supported inputs:

- raw `complex64` IQ captures
- WAV captures
- individual files
- directories of captures

Output targets:

- terminal summaries
- JSON documents
- JSONL event streams
- SQLite event databases

## Safety boundary

Use this only with your own hardware, your own lab captures, or systems you are explicitly authorized to observe. Keep this passive. Do not use it to target third-party devices, private communications, or restricted radio services.

## Install

Kali treats the system Python as externally managed, so use a virtualenv:

```bash
cd /home/smith/codex/software/local/burstwatch
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Command overview

```bash
burstwatch analyze <capture>
burstwatch scan <capture-or-dir> [more inputs...]
burstwatch fingerprint <capture-or-dir> [more inputs...]
burstwatch baseline <scan.json> [more scan json files...]
burstwatch watch <baseline.json> <capture-or-dir> [more inputs...]
burstwatch menu
```

## Quick start

Analyze one saved IQ capture:

```bash
burstwatch analyze capture.c64 --sample-rate 2400000 --center-freq 433920000
```

Scan a directory of saved captures and write both summary and raw events:

```bash
burstwatch scan captures/433/ \
  --sample-rate 2400000 \
  --center-freq 433920000 \
  --recursive \
  --json-out runs/433-scan.json \
  --event-jsonl runs/433-events.jsonl \
  --event-sqlite runs/433-events.sqlite3
```

Build fingerprints from the same capture set:

```bash
burstwatch fingerprint captures/433/ \
  --sample-rate 2400000 \
  --center-freq 433920000 \
  --recursive \
  --name-prefix lab433 \
  --json-out runs/433-fingerprints.json
```

Build a baseline from prior scan summaries:

```bash
burstwatch baseline runs/day1-scan.json runs/day2-scan.json runs/day3-scan.json \
  --json-out runs/433-baseline.json
```

Watch a fresh capture batch against the saved baseline:

```bash
burstwatch watch runs/433-baseline.json captures/new/ \
  --sample-rate 2400000 \
  --center-freq 433920000 \
  --recursive \
  --json-out runs/433-watch.json
```

Launch the responsive Rich menu:

```bash
burstwatch menu
```

The menu adds:

- a multicolor ASCII header on wide terminals
- a compact fallback header on narrow terminals
- guided prompts for all five workflows
- Rich tables and panels for result summaries

## Advanced workflows

### 1. Unknown-emitter discovery in one band

Use `scan` when you want passive device discovery, not packet decoding.

```bash
burstwatch scan captures/ism-433/ \
  --sample-rate 2400000 \
  --center-freq 433920000 \
  --recursive \
  --freq-bin-hz 5000
```

What you get:

- emitter candidate IDs such as `emitter-001`
- approximate frequencies
- dominant labels such as `ook_ask`, `fsk`, or `chirp`
- burst counts, bandwidth, and mean duration

### 2. Raw-event pipeline for later Elastic ingestion

If you care about every burst, not just clustered emitters:

```bash
burstwatch scan captures/433/ \
  --sample-rate 2400000 \
  --center-freq 433920000 \
  --event-jsonl runs/433-events.jsonl \
  --event-sqlite runs/433-events.sqlite3 \
  --json-out runs/433-scan.json
```

This gives you:

- per-burst JSONL for log pipelines
- SQLite for local filtering and ad hoc review
- clustered scan JSON for higher-level inventory work

### 3. Passive fingerprints for your own sensors

If you have several recurring devices in a lab and want reusable profiles:

```bash
burstwatch fingerprint captures/lab-session-a/ captures/lab-session-b/ \
  --sample-rate 1024000 \
  --center-freq 915000000 \
  --recursive \
  --freq-bin-hz 10000 \
  --name-prefix lab915
```

Each fingerprint includes:

- approximate frequency
- dominant burst label
- duration range
- bandwidth range
- duty cycle mean
- repetition interval mean and standard deviation when available

### 4. Environment baseline and anomaly watch

Baseline:

```bash
burstwatch baseline runs/morning.json runs/afternoon.json runs/evening.json \
  --freq-bin-hz 5000 \
  --json-out runs/lab-baseline.json
```

Watch:

```bash
burstwatch watch runs/lab-baseline.json captures/fresh/ \
  --sample-rate 2400000 \
  --center-freq 433920000 \
  --recursive
```

This is the intended defensive flow for:

- new emitter appeared
- same emitter but bandwidth changed
- same emitter but duration or duty cycle changed
- same emitter but the burst label shifted

### 5. Narrow-band sweep batches

If you export one capture per tuned step from GNU Radio or another recorder:

```bash
burstwatch scan captures/sweep-step-1.c64 captures/sweep-step-2.c64 captures/sweep-step-3.c64 \
  --sample-rate 2048000 \
  --center-freq 315000000 \
  --freq-bin-hz 10000
```

That is the current answer to passive “scanning” in this repo: you save the captures first, then `burstwatch` inventories them.

### 6. WAV-only lab review

For intermediate audio captures or demodulated lab recordings:

```bash
burstwatch analyze audio.wav
burstwatch scan wav-captures/ --recursive
```

## Input assumptions

- `complex64` inputs require `--sample-rate`
- `--center-freq` is optional but strongly recommended for meaningful emitter inventories
- directory inputs default to `*.c64` and `*.wav`
- use `--pattern` repeatedly when you want narrower directory selection

Example:

```bash
burstwatch scan captures/ \
  --sample-rate 2400000 \
  --center-freq 433920000 \
  --pattern "*.c64" \
  --pattern "*.wav"
```

## GNU Radio handoff

The intended live workflow is:

1. Use GNU Radio, `rtl_sdr`, or another receiver to save a capture.
2. Run `burstwatch analyze` or `burstwatch scan` on that capture.
3. Use `fingerprint`, `baseline`, and `watch` to build durable passive discovery workflows.

This keeps the command layer testable and auditable before any future live-capture work.

## Output shape

`analyze` emits per-burst events with:

- capture path
- timing span
- label and confidence
- bandwidth
- duty cycle
- tone counts
- chirp slope

`scan` emits emitter candidates with:

- candidate ID
- approximate frequency
- dominant label
- label counts
- burst count
- duration and bandwidth ranges
- repetition interval statistics when visible

`baseline` emits stable records with:

- baseline ID
- expected label
- expected bandwidth and duration
- expected burst counts
- frequency tolerance

`watch` emits alert entries with:

- `new` for unseen emitters
- `changed` for emitters that drifted beyond the learned baseline

## Verification

Current repo checks:

```bash
PYTHONPATH=src python3 -m compileall src tests
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m burstwatch --help
```

## Next step

The next logical pass is deeper menu polish or a live-capture helper that feeds these same workflows without replacing them.
