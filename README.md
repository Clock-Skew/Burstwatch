# burstwatch

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![GNU Radio](https://img.shields.io/badge/GNU%20Radio-capture%20friendly-FF6600)](https://www.gnuradio.org/)
[![RTL-SDR](https://img.shields.io/badge/RTL--SDR-passive%20IQ-00599C)](https://osmocom.org/projects/rtl-sdr/wiki/Rtl-sdr)
[![Rich](https://img.shields.io/badge/Rich-terminal%20UI-CC3366)](https://github.com/Textualize/rich)
[![NumPy](https://img.shields.io/badge/NumPy-signal%20arrays-013243?logo=numpy&logoColor=white)](https://numpy.org/)
[![License MIT](https://img.shields.io/badge/License-MIT-2EA44F.svg)](https://opensource.org/license/mit)

`burstwatch` is a passive RF burst analysis toolkit for saved SDR captures. It helps you record or import IQ files, find burst activity, classify rough signal shapes, cluster likely emitters, build fingerprints, learn a baseline, and compare later captures for new or changed RF activity.

It is designed for owned hardware, lab devices, and authorized research. It does not transmit. It does not decode private traffic. It does not make third-party systems yours to inspect.

## Legal Boundary

Use `burstwatch` only with your own equipment, your own lab captures, public/broadcast signals you are legally allowed to receive, or systems where you have explicit written authorization. Radio monitoring rules vary by country and service. Do not use this project to intercept private communications, target vehicles, target public-safety systems, collect cellular subscriber data, or profile third-party devices in the wild.

The project intentionally works from saved captures and passive metadata: frequency, burst timing, approximate bandwidth, rough signal shape, repetition patterns, and changes against a baseline.

## Features

- `capture`: record passive RTL-SDR IQ to `complex64`, then optionally analyze or scan it
- `analyze`: classify bursts in one IQ or WAV capture
- `scan`: cluster bursts into passive emitter candidates
- `fingerprint`: derive reusable passive RF fingerprints
- `baseline`: learn normal emitter profiles from prior scans
- `watch`: compare a fresh scan against a saved baseline
- `dashboard`: summarize recent `burstwatch` JSON artifacts
- `menu`: launch the responsive Rich terminal menu with a multicolor ASCII banner

## Install

Kali and other modern Linux distributions may mark the system Python as externally managed, so use a virtual environment:

```bash
cd /home/smith/codex/software/local/burstwatch
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Optional SDR-side tools:

```bash
sudo apt update
sudo apt install -y rtl-sdr gnuradio gqrx-sdr
```

`rtl_sdr` is only needed for the `capture` command. GNU Radio and Gqrx are useful for recording, inspecting, and exporting captures before handing files to `burstwatch`.

## Quick Start

Launch the guided terminal UI:

```bash
burstwatch menu
```

The dashboard does not scan the radio and it does not create files. It only shows saved `burstwatch` JSON outputs from `runs/`. If you open it before creating any JSON, it says:

```text
No JSON yet.
```

Create a first JSON artifact from an existing capture:

```bash
burstwatch scan captures/433/ \
  --sample-rate 2400000 \
  --center-freq 433920000 \
  --recursive \
  --json-out runs/433-scan.json
```

Then open the dashboard:

```bash
burstwatch dashboard runs
```

Record a short passive capture from an RTL-SDR dongle:

```bash
burstwatch capture captures/433920000-lab.c64 \
  --center-freq 433920000 \
  --sample-rate 2400000 \
  --duration 10 \
  --metadata-json runs/433-capture.json
```

Record, then immediately scan the saved file:

```bash
burstwatch capture captures/433920000-lab.c64 \
  --center-freq 433920000 \
  --sample-rate 2400000 \
  --duration 10 \
  --then scan
```

Analyze one saved IQ capture:

```bash
burstwatch analyze captures/433920000-lab.c64 \
  --sample-rate 2400000 \
  --center-freq 433920000
```

Scan a directory of captures:

```bash
burstwatch scan captures/433/ \
  --sample-rate 2400000 \
  --center-freq 433920000 \
  --recursive \
  --json-out runs/433-scan.json \
  --event-jsonl runs/433-events.jsonl \
  --event-sqlite runs/433-events.sqlite3
```

Review saved JSON outputs:

```bash
burstwatch dashboard runs --limit 20
```

## GNU Radio Handoff

`burstwatch` expects raw `complex64` IQ or WAV input. In GNU Radio Companion, a simple file-first flow is:

```text
RTL-SDR Source
-> Frequency Xlating FIR Filter or direct pass-through
-> File Sink
```

Set the file sink to write complex samples, record a short capture, then analyze it:

```bash
burstwatch scan captures/gnu-radio-step.c64 \
  --sample-rate 2048000 \
  --center-freq 915000000 \
  --freq-bin-hz 10000
```

## Advanced Use

Unknown-emitter discovery:

```bash
burstwatch scan captures/ism-433/ \
  --sample-rate 2400000 \
  --center-freq 433920000 \
  --recursive \
  --freq-bin-hz 5000 \
  --json-out runs/ism-433-scan.json
```

Passive fingerprints for your own lab sensors:

```bash
burstwatch fingerprint captures/lab-session-a/ captures/lab-session-b/ \
  --sample-rate 1024000 \
  --center-freq 915000000 \
  --recursive \
  --freq-bin-hz 10000 \
  --name-prefix lab915 \
  --json-out runs/lab915-fingerprints.json
```

Environment baseline:

```bash
burstwatch baseline runs/morning-scan.json runs/afternoon-scan.json runs/evening-scan.json \
  --freq-bin-hz 5000 \
  --json-out runs/lab-baseline.json
```

Watch for changes:

```bash
burstwatch watch runs/lab-baseline.json captures/fresh/ \
  --sample-rate 2400000 \
  --center-freq 433920000 \
  --recursive \
  --json-out runs/lab-watch.json
```

Narrow-band sweep batches:

```bash
burstwatch scan captures/sweep-step-1.c64 captures/sweep-step-2.c64 captures/sweep-step-3.c64 \
  --sample-rate 2048000 \
  --center-freq 315000000 \
  --freq-bin-hz 10000
```

JSONL pipeline for Elastic or another SOC stack:

```bash
burstwatch scan captures/433/ \
  --sample-rate 2400000 \
  --center-freq 433920000 \
  --event-jsonl runs/433-events.jsonl \
  --json-out runs/433-scan.json
```

## Output Model

`burstwatch` writes reviewable local artifacts:

- scan summaries: clustered emitter candidates and label counts
- fingerprint summaries: reusable passive profiles for recurring devices
- baselines: normal RF profiles learned from prior scans
- watch reports: new or changed emitter alerts against a baseline
- JSONL events: one line per burst for log pipelines
- SQLite events: local filtering and ad hoc review

## Development

Run the test suite:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Run compile checks:

```bash
PYTHONPATH=src python3 -m compileall src tests
```

## License

MIT. See [LICENSE](LICENSE).
