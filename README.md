# GBN Lab — Go-Back-N ARQ Protocol Simulator

![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB.svg)
![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)

An interactive, real-time visualisation of the **Go-Back-N Automatic Repeat reQuest (ARQ)** protocol — the sliding-window error-control mechanism at the heart of reliable data link layer communication.

GBN Lab turns protocol internals into a live animation: watch packets fly across the channel, ACKs return, timers fire, and windows slide as you introduce bit errors and packet loss. Built for students, instructors, and anyone who learns better by seeing.

---

## Table of Contents

- [Features](#features)
- [How It Works](#how-it-works)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Quick Start](#quick-start)
  - [Manual Setup](#manual-setup)
- [Usage Guide](#usage-guide)
- [Project Structure](#project-structure)
- [Contributing](#contributing)

---

## Features

- **Real-time packet animation** — sender, channel, and receiver rendered on a single canvas; packets, ACKs, timeouts, and window slides are all visible as they happen
- **Configurable channel impairments** — live sliders for window size, bit error rate (BER), packet loss rate, packet count, and simulation speed
- **Scenario presets** — one-click environments: *Low Errors*, *Moderate Noise*, *High BER Nightmare*, *Packet Loss Hell*
- **Adaptive timeout** — timeout auto-calibrates to 3× RTT, so you can focus on the protocol, not tuning timers
- **Step-by-step mode** — pauses automatically at anomalies (timeouts, corruption, loss) for classroom-style walkthroughs
- **Post-run replay** — scrub through the entire session with a timeline slider and step controls
- **Live performance metrics** — efficiency over time, packets lost/corrupted, and completion stats updated in real time
- **Event log** — timestamped, colour-coded trail of every protocol event

## How It Works

Go-Back-N is a sliding-window ARQ scheme:

1. The sender transmits up to **N** frames without waiting for an ACK (a *window* of in-flight frames).
2. The receiver accepts only in-order frames and returns a **cumulative ACK** for the highest consecutive frame received.
3. On a **timeout** for the oldest unacknowledged frame, the sender retransmits **all** frames from that point onward — "going back N".
4. Damaged or lost frames trigger the same retransmission; the receiver silently discards anything out of order.

GBN Lab simulates this loop frame-by-frame over a noisy channel, letting you watch exactly how window size and error rate trade off against throughput and efficiency.

## Getting Started

### Prerequisites

- **Python 3.9+**
- A display (the app is GUI-based; no headless mode)

### Quick Start

Install everything and launch in one command:

```bash
# macOS / Linux
./setup.sh run

# Windows
setup.bat run
```

Install only (launch later):

```bash
# macOS / Linux
./setup.sh

# Windows
setup.bat
```

### Manual Setup

```bash
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
# OR
venv\Scripts\activate           # Windows

pip install -r requirements.txt
python app.py
```

## Usage Guide

1. **Pick a scenario** from the dropdown — or tune the sliders yourself (window size `N`, BER, packet loss, packet count, speed).
2. **Run** the simulation and watch packets animate across the channel.
3. Toggle **Step-by-Step mode** to pause at each anomaly and examine the protocol's response.
4. After completion, use the **Replay** scrubber to re-walk the session frame-by-frame and inspect the event log.
5. Read the final **efficiency** and channel statistics in the metrics panel.

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
├── setup.sh           # macOS / Linux installer
├── setup.bat          # Windows installer
├── requirements.txt   # Python dependencies
└── CHANGELOG.md       # Version history
```

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide.

1. Fork the repository and create a feature branch.
2. Keep changes focused and well-tested.
3. Update the README and CHANGELOG where relevant.
4. Open a pull request with a clear description.
