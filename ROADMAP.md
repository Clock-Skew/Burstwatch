# burstwatch roadmap

## MODE

- Passive receive-only analysis
- Own or authorized captures only
- File-first workflow before live SDR integration

## SCOPE

- Load complex IQ captures and WAV captures
- Detect burst windows with an adaptive envelope threshold
- Extract simple burst features from time and frequency domains
- Classify burst shape with rule-based heuristics
- Export JSONL and SQLite event logs
- Keep the first pass small and testable

## DONE

- Repo scaffold exists in `software/local/burstwatch`
- CLI can analyze a capture file
- Synthetic tests cover the main label families
- JSONL and SQLite output paths are wired

## VERIFY

- `python -m unittest`
- `python -m burstwatch --help`
- `burstwatch analyze <capture> --sample-rate ...`

## CONSTRAINTS

- No transmit path
- No private comms interception
- No cellular, vehicle, or third-party device targeting
- Keep dependencies small and the code easy to audit

