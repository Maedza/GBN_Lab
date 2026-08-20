# Changelog

All notable changes to GBN Lab are documented here.

## [Unreleased]

### Changed
- Splash screen now dismisses in ~1s instead of ~5s
- `app.py` is the single entry point — `main.py` removed; setup scripts and README updated
- Refactored `app.py` into five mixin modules: `ui_builder.py`, `sim_control.py`,
  `replay_control.py`, `event_log.py`, `canvas_render.py` (behavior unchanged)
- Replay frame / log text caps moved to `config.py` (`MAX_REPLAY_FRAMES`, `MAX_LOG_TEXT_LINES`)

## [Stable]

### Changed
- Multiple flying packets render simultaneously during transmission
- Receiver viewport follows sender (syncs to base frame)
- Replay ends with clean completion frames — all packets delivered/green; DONE event shows final metrics
- Removed redundant comments and section headers across all files

### Fixed
- Memory safety caps for replay frames and log text
- Duplicate ACK looping on corrupted packets
- Cross-platform monospace font (was macOS-only SF Mono)
- Labels at x=40 and grid boxes at x=125 synced

### Added
- Packet loss slider (default 5%)
- Branded splash screen + near-fullscreen main window
- Setup scripts (`setup.sh`, `setup.bat`), README, `.gitignore`

## [0.1.0] — Rebuild

### Added
- Go-Back-N ARQ simulation platform — full rebuild
