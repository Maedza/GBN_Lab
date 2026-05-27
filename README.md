# GBN Lab — Go-Back-N ARQ Simulator

Interactive visual simulation of the Go-Back-N Automatic Repeat Request protocol.

## Quick Start

**macOS / Linux:**
```bash
./setup.sh        # creates venv, installs deps
python main.py    # launches the simulator
```

**Windows (double-click or run):**
```
setup.bat         # creates venv, installs deps
python main.py    # launches the simulator
```

## What It Shows

- Real-time packet animation across sender → channel → receiver
- Slider controls for BER, packet loss, timeout, window size, speed
- Scenario presets: Low Errors, Moderate Noise, High BER, Packet Loss
- Step-by-step mode pausing on anomalies
- Post-simulation replay with timeline scrubber

## Requirements

- Python 3.9+
- `customtkinter` (auto-installed by setup script)
