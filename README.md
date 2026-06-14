# GBN Lab — Go-Back-N ARQ Simulator

Interactive visual simulation of the Go-Back-N Automatic Repeat Request protocol.

## Quick Start

```bash
./setup.sh        # creates venv, installs deps
python main.py    # launches the simulator
```

## What It Shows

- Real-time packet animation across sender → channel → receiver
- Slider controls for BER, packet loss, timeout, window size, speed
- Scenario presets: Low Errors, Moderate Noise, High BER, Packet Loss
- Step-by-step mode pausing on anomalies
- Post-simulation replay with timeline scrubber
- Live efficiency-over-time chart in the metrics panel

## Requirements

- Python 3.9+
- `customtkinter>=5.2.0` (see `requirements.txt`)
