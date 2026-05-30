# burstwatch

Passive RF burst detector and shape classifier for owned or authorized captures.

`burstwatch` is a first-pass lab tool for:

- spotting new transmit bursts in IQ captures
- extracting simple envelope and spectrum features
- labeling bursts as `ook_ask`, `fsk`, `chirp`, `fm_like`, `narrowband_digital`, or `unknown`
- exporting JSONL and SQLite event logs for later analysis or Elastic ingestion

It is intentionally passive. It does not transmit.

## Recommended model

- Use `standard` for implementation work.
- Use `deep` for feature tuning, signal-shape heuristics, or hard-to-explain RF behavior.
- Use `quick` for short status checks and small follow-up edits.

## First-pass roadmap

See [ROADMAP.md](ROADMAP.md).

## Install

```bash
cd /home/smith/codex/software/local/burstwatch
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Quick start

Analyze a complex IQ file exported from GNU Radio:

```bash
burstwatch analyze capture.c64 --sample-rate 2400000 --center-freq 433920000
```

Write JSONL and SQLite outputs:

```bash
burstwatch analyze capture.c64 \
  --sample-rate 2400000 \
  --center-freq 433920000 \
  --jsonl runs/bursts.jsonl \
  --sqlite runs/bursts.sqlite3
```

Analyze a WAV capture:

```bash
burstwatch analyze audio.wav
```

## GNU Radio handoff

For live experiments, use GNU Radio to write a capture file, then run `burstwatch` on the saved samples.
The first pass is file-based on purpose so the detection and classification logic stays easy to test.

## Output shape

Each burst event includes:

- source path
- sample rate
- optional center frequency
- burst span in samples and seconds
- label and confidence
- feature bundle with envelope and spectrum metrics
- notes from the classifier

That JSON is suitable for later conversion into Elastic documents or a local dashboard.

