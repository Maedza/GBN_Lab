# Contributing to GBN Lab

Thanks for taking the time to contribute. This document outlines how to get set up, what we expect from pull requests, and how to keep the codebase healthy.

## Table of Contents

- [Development Setup](#development-setup)
- [Code Style](#code-style)
- [How to Contribute](#how-to-contribute)
- [Pull Request Template](#pull-request-template)
- [Pull Request Checklist](#pull-request-checklist)
- [Project Structure](#project-structure)

## Development Setup

```bash
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
# OR
venv\Scripts\activate           # Windows

pip install -r requirements.txt
python app.py
```

## Code Style

- **Python 3.9+** compatible syntax only.
- Keep code **clean and efficient** — performance and readability first.
- **Minimize comments.** Only add them where logic is genuinely non-obvious.
- **Prefer the shortest correct solution.** No speculative abstractions, no over-engineered patterns — implement exactly what the feature needs.
- **Write all code, identifiers, and commit messages in English.**
- **Commit messages are one line** — a single imperative sentence summarising the change (e.g. `fix: cap replay frame buffer`). No bodies, no blank lines.
- Match the existing style: type hints on signatures, mixin modules for behaviour, shared constants in `config.py`.

## How to Contribute

1. **Open an issue** first for bugs or feature ideas, or comment on an existing one to claim it.
2. **Fork** the repository and create a feature branch:

   ```bash
   git checkout -b feature/your-feature-name
   ```

3. Make your changes, keeping them **focused** — one logical change per PR.
4. **Test** that the app still launches and the relevant flows work:

   ```bash
   python app.py
   ```

5. Update the **README** where user-facing behaviour changes, and add an entry to **CHANGELOG.md** under `[Unreleased]`.
6. Push and open a pull request — copy the template below and complete every section.

## Pull Request Template

```markdown
## Summary

<!-- What does this PR do, and why? Keep it to 2-3 sentences. -->

## Changes

<!-- Bullet list of the key changes, one per line. -->

-

## Testing

<!-- How was this verified? e.g. app launches, scenario X run, replay checked. -->

- [ ] `python app.py` launches without errors
- [ ] Affected flow(s) smoke-tested

## Related

<!-- Link any issues this closes: "Closes #123" or "Related to #456". -->

Closes #

## Checklist

- [ ] Single, focused change
- [ ] One-line commit message(s)
- [ ] CHANGELOG entry added under `[Unreleased]`
- [ ] README updated if user-facing behaviour changed
```

## Project Structure

```
├── app.py             # Entry point — window, splash, event loop
├── config.py          # Constants, colour scheme, scenario presets
├── simulation.py      # Go-Back-N protocol engine
├── ui_builder.py      # UI construction (panels, sliders, metrics)
├── sim_control.py     # Run / stop / step simulation control
├── replay_control.py  # Replay capture, seek, and playback
├── event_log.py       # Event tracking and log rendering
├── canvas_render.py   # Animation canvas and all drawing
├── splash.py          # Startup splash screen
└── setup.sh/.bat      # Platform installers
```

**Tip:** `app.py` is intentionally a thin shell — new behaviour belongs in the relevant mixin, shared constants go in `config.py`, and protocol logic lives in `simulation.py`.
