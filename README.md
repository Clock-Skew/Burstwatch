# burstwatch

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![GNU Radio](https://img.shields.io/badge/GNU%20Radio-capture%20friendly-FF6600)](https://www.gnuradio.org/)
[![RTL-SDR](https://img.shields.io/badge/RTL--SDR-passive%20IQ-00599C)](https://osmocom.org/projects/rtl-sdr/wiki/Rtl-sdr)
[![Rich](https://img.shields.io/badge/Rich-terminal%20UI-CC3366)](https://github.com/Textualize/rich)
[![NumPy](https://img.shields.io/badge/NumPy-signal%20arrays-013243?logo=numpy&logoColor=white)](https://numpy.org/)
[![License MIT](https://img.shields.io/badge/License-MIT-2EA44F.svg)](https://opensource.org/license/mit)

`burstwatch` is a passive RF signal workspace for learning what your own SDR can see. It can launch helper tools, record a short capture, scan it, save the results, and keep the next step inside one terminal menu.

It is designed for owned hardware, lab devices, and authorized research. It does not transmit. It does not decode private traffic. It does not make third-party systems yours to inspect.

## Legal Boundary

Use `burstwatch` only with your own equipment, your own lab captures, public/broadcast signals you are legally allowed to receive, or systems where you have explicit written authorization. Radio monitoring rules vary by country and service. Do not use this project to intercept private communications, target vehicles, target public-safety systems, collect cellular subscriber data, or profile third-party devices in the wild.

The project intentionally works from saved captures and passive metadata: frequency, burst timing, approximate bandwidth, rough signal shape, repetition patterns, and changes against a baseline.

## What You Do

Use the menu first:

```bash
burstwatch menu
```

Then choose:

- `1 Start a session` to pick a practical RF path
- `2 Signal board` to see saved results and next actions
- `3 Signal ideas` to browse passive vectors, bands, and detection methods
- `4 Receiver tools` to test RTL-SDR or launch Gqrx / GNU Radio

The menu handles the normal handoff:

- records or accepts a capture
- scans the capture
- saves result JSON into `runs/`
- saves raw burst events into `runs/`
- sends you back to the signal board

The lower-level commands still exist for advanced users, but they are not the main workflow.

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

`rtl_sdr` is used for recording. Gqrx and GNU Radio Companion can be opened from the Burstwatch menu when installed.

## Quick Start

Start a session:

```bash
burstwatch menu
```

Choose `1 Start a session`.

For a first RTL-SDR run, the menu will:

- show the passive/authorization boundary
- check whether helper tools are installed
- optionally run `rtl_test`
- ask for a common band or custom frequency
- record a short passive IQ capture
- scan it automatically
- write results into `captures/` and `runs/`
- show the next signal-board step

If you already have a capture, choose `6 Open a capture`. Burstwatch will ask for the file or folder, scan it, and write result files for you.

## Signal Board

The signal board is the home screen for results. It reads saved outputs from `runs/`.

If nothing has been saved yet, it says:

```text
No JSON yet.
```

That means: run `Start a session`, `Record from SDR`, or `Open a capture` first.

After a scan, use:

```bash
burstwatch menu
```

Then choose `2 Signal board`.

## Tool Launcher

Choose `4 Receiver tools` from the menu to:

- run `rtl_test`
- open Gqrx
- open GNU Radio Companion
- see install commands for missing tools

This keeps third-party tools inside the same workflow instead of making you remember separate commands.

## Passive Field Guide

Choose `3 Signal ideas` in the menu for these examples and matching capture defaults.

| Path | Center | Examples | What Burstwatch Looks For |
| --- | ---: | --- | --- |
| 433 MHz home/lab sensors | 433.920 MHz | Owned weather stations, contact sensors, outlet remotes, soil sensors | OOK/ASK bursts, repetition timing, rough bandwidth, baseline changes |
| 315 MHz low-power devices | 315.000 MHz | Owned remotes, lab transmitters, your own TPMS presence checks | Short bursts, duty cycle, time gaps, new-emitter alerts |
| 902-928 MHz ISM activity | 915.000 MHz | Owned LoRa-style modules, lab sensors, hobby telemetry | FSK/chirp-like shapes, channel occupancy, recurring emitters |
| 137 MHz NOAA practice | 137.100 MHz | Public NOAA APT satellite passes | Waterfall review, signal presence, Doppler awareness |
| 1090 MHz ADS-B study | 1090.000 MHz | Public aircraft broadcast visibility | Burst density and later trust-analysis ideas |
| FM receiver check | 100.100 MHz | A known local FM broadcast station | Receiver, antenna, gain, and sample-rate sanity |

Useful passive approaches:

- **Burst discovery**: find short transmissions that appear and disappear quickly.
- **Shape labeling**: separate OOK/ASK, FSK, chirp-like, and FM-like activity.
- **Repetition timing**: spot devices that transmit every few seconds or minutes.
- **Frequency grouping**: cluster repeated bursts near the same center frequency.
- **Baseline and watch**: learn a local pattern, then flag new or changed emitters.
- **Waterfall first**: use Gqrx before capture when you need visual confidence.
- **SOC handoff**: export JSONL and feed events into Elastic, Logstash, or another timeline.

Boundaries still matter. Keep private communications, third-party vehicles, public-safety systems, and cellular subscriber data out of scope unless you have explicit written authorization and the right tooling/legal basis.

## What Files Mean

Burstwatch uses two main folders:

- `captures/`: saved radio captures, usually `.c64`
- `runs/`: saved result outputs, usually `.json` and `.jsonl`

Common saved files:

- `*-capture.json`: metadata for a recording
- `*-scan.json`: emitter candidates found in a capture
- `*-events.jsonl`: one burst event per line
- `baseline.json`: local RF pattern learned from scan files
- `*-watch.json`: new or changed activity compared to a baseline

## Manual Commands

The menu is the intended path. These commands are for repeatable or advanced use.

Record a short passive capture:

```bash
burstwatch capture captures/433920000-lab.c64 \
  --center-freq 433920000 \
  --sample-rate 2400000 \
  --duration 10 \
  --metadata-json runs/433-capture.json
```

Scan a saved capture or folder:

```bash
burstwatch scan captures/433/ \
  --sample-rate 2400000 \
  --center-freq 433920000 \
  --recursive \
  --json-out runs/433-scan.json
```

Review saved outputs:

```bash
burstwatch dashboard runs
```

Analyze one saved IQ capture:

```bash
burstwatch analyze captures/433920000-lab.c64 \
  --sample-rate 2400000 \
  --center-freq 433920000
```

## GNU Radio Handoff

The menu can open GNU Radio Companion from `4 Receiver tools`.

`burstwatch` expects raw `complex64` IQ or WAV input. In GNU Radio Companion, a simple file-first flow is:

```text
RTL-SDR Source
-> Frequency Xlating FIR Filter or direct pass-through
-> File Sink
```

Set the file sink to write complex samples, record a short capture, then return to `burstwatch menu` and choose `6 Open a capture`.

Manual scan:

```bash
burstwatch scan captures/gnu-radio-step.c64 \
  --sample-rate 2048000 \
  --center-freq 915000000 \
  --freq-bin-hz 10000
```

## Advanced Use

Menu-first examples:

```text
burstwatch menu
1 Start a session
3 Open an existing capture
```

```text
burstwatch menu
3 Signal ideas
1 433 MHz home/lab sensors
1 Record this center frequency with RTL-SDR
```

```text
burstwatch menu
2 Signal board
2 Build baseline or watch for changes
```

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
