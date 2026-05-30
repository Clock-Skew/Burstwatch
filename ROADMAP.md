# burstwatch roadmap

## Current Mode

- Receive-only SDR capture and saved-file analysis.
- Owned devices, lab devices, public broadcasts, or written authorization.
- Menu-first operator flow with CLI commands kept for repeatable automation.
- Local artifacts in `captures/` and `runs/`.

## Current Scope

- Load complex IQ captures and WAV captures.
- Record passive RTL-SDR IQ through `rtl_sdr`.
- Detect burst windows with an adaptive envelope threshold.
- Extract simple time/frequency features.
- Classify rough signal shape with rule-based heuristics.
- Cluster likely emitter candidates.
- Build fingerprints, baselines, and watch reports.
- Export JSON, JSONL, and SQLite event logs.
- Launch receiver tools from the terminal workspace.

## UX Direction

- Keep the main menu calm, short, and practical.
- Avoid clearing the terminal between screens so keypad state is not disturbed.
- Keep menu input on direct stdin reads instead of line-editing helpers so terminal keypad state stays untouched.
- Prefer "session", "signal board", "receiver tools", and "signal ideas" over training-wheel language.
- Put examples inside the flow before asking for technical values.
- Keep advanced flags available without making them the first experience.

## Passive Vectors To Add

- Frequency sweep sessions: step through a band plan and merge results into one board.
- Time-of-day baselines: compare morning, afternoon, evening, and overnight RF patterns.
- Duty-cycle reports: identify devices that transmit unusually often.
- Drift tracking: flag emitters whose center frequency moves over time.
- Burst interval fingerprints: group devices by timing pattern, not just frequency.
- Gqrx bookmark export/import: make visual exploration feed capture presets.
- NOAA and ADS-B handoff notes: point users to purpose-built decoders while keeping Burstwatch as the metadata layer.
- Elastic/Logstash profile: ship a ready JSONL ingest example for Kali Purple.

## Authorized Expansion Roadmap

This phase should remain permission-first. "More active" means scoped, logged, and reversible work against owned lab systems or written authorization, not public RF targeting.

1. Scope profiles

- Add a `scope.json` or `project.yaml` that records allowed devices, bands, networks, owners, dates, and notes.
- Refuse active modules unless a scope profile exists.
- Store every run with the scope identifier.

2. Aggregation layer

- Combine RF captures, Gqrx notes, GNU Radio file metadata, local network inventory, firmware files, mobile-app artifacts, and manual notes into one project timeline.
- Keep raw evidence local and export sanitized reports.
- Add deduplication so repeated captures collapse into stable device candidates.

3. Local network discovery for owned labs

- Add optional mDNS, SSDP/UPnP, ARP table, and DHCP lease import for the user's own network.
- Correlate device names, MAC OUIs, IPs, and RF events when the user has permission.
- Keep it read-only first.

4. Device research workspace

- Add per-device folders for photos, FCC IDs, manuals, firmware, captures, and notes.
- Add static firmware inventory: strings, file types, hashes, certificates, update URLs, and exposed configs.
- Add mobile-app static notes for companion apps when the user owns the device or has authorization.

5. Controlled active checks

- Add gated checks for owned lab services: HTTP headers, TLS posture, default pages, auth presence, and update endpoints.
- Keep request volume low, log every request, and require explicit confirmation.
- Do not add exploit, replay, jamming, bypass, or credential-attack workflows.

6. Reporting and disclosure

- Generate a public-safe report template from evidence.
- Separate "observed", "inferred", and "needs validation" sections.
- Include remediation language for weak telemetry, noisy broadcasts, missing auth, and poor update hygiene.

## Verification

- `PYTHONPATH=src python3 -m compileall src tests`
- `PYTHONPATH=src python3 -m unittest discover -s tests -v`
- `PYTHONPATH=src python3 -m burstwatch --help`
- `PYTHONPATH=src python3 -m burstwatch tools`
- scripted `burstwatch menu` smokes for Signal board, Signal ideas, Receiver tools, and Open a capture

## Constraints

- No transmit path in the current project.
- No private communications interception.
- No cellular subscriber collection.
- No vehicle/key replay or third-party vehicle targeting.
- No public-safety targeting.
- Keep dependencies small and the code easy to audit.
