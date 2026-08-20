"""
Go-Back-N Protocol Simulator — Configuration & Constants.
"""

from __future__ import annotations
import sys as _sys

_REFERENCE_WIDTH = 1920
_REFERENCE_HEIGHT = 1080
CANVAS_SCALE: float = 1.0

_PLATFORM_BOOST = 1.35 if _sys.platform == "win32" else 1.0


def init_scale(sw: int, sh: int) -> float:
    """Compute screen-density scale factor. Call once at app startup."""
    global CANVAS_SCALE
    
    if _sys.platform == "darwin":
        CANVAS_SCALE = 1.0
        return CANVAS_SCALE

    w_ratio = sw / _REFERENCE_WIDTH
    h_ratio = sh / _REFERENCE_HEIGHT
    area_ratio = (w_ratio + h_ratio) / 2.0
    CANVAS_SCALE = area_ratio * _PLATFORM_BOOST
    CANVAS_SCALE = max(1.12, min(CANVAS_SCALE, 1.8))
    return CANVAS_SCALE


DEFAULT_WINDOW_SIZE = 4
DEFAULT_BER = 0.0001
DEFAULT_PACKET_LOSS = 0.05
DEFAULT_NUM_PACKETS = 10
DEFAULT_TIMEOUT_MS = 0
DEFAULT_PACKET_SIZE_BITS = 1000
DEFAULT_DATA_RATE_KBPS = 100
DEFAULT_PROPAGATION_DELAY_MS = 10
DEFAULT_SIM_SPEED = 0.2

GUI_UPDATE_INTERVAL_MS = 50
MAX_LOG_EVENTS = 80
MAX_REPLAY_FRAMES = 2000
MAX_LOG_TEXT_LINES = 500

ANIMATION_INTERVAL_MS = 80
MONO_FONT = ("Consolas", "SF Mono", "Courier New", "TkFixedFont")
PACKET_BOX_RATIO = 0.048
PACKET_SPACING_RATIO = 0.008

CANVAS_SENDER_Y_RATIO = 0.12
CANVAS_RECV_Y_RATIO = 0.68
CANVAS_MARGIN_RATIO = 0.03
CANVAS_LABEL_X_RATIO = 0.03
CANVAS_GRID_OFFSET_RATIO = 0.10
CANVAS_FOOTER_RATIO = 0.04
CANVAS_LEGEND_W_RATIO = 0.12
CANVAS_WEIGHT = 3
EVENT_LOG_WEIGHT = 2
EVENT_LOG_HEIGHT = 10

COLOR_BG = "#0f172a"
COLOR_BG_PANEL = "#1e293b"
COLOR_BG_HIGHLIGHT = "#334155"
COLOR_ACCENT = "#38bdf8"
COLOR_BRAND = "#6366f1"
COLOR_SUCCESS = "#4ade80"
COLOR_ERROR = "#f87171"
COLOR_WARNING = "#fbbf24"
COLOR_TEXT = "#f1f5f9"
COLOR_TEXT_MUTED = "#94a3b8"
COLOR_BORDER = "#334155"

COLOR_UNSENT = "#334155"
COLOR_SENT = COLOR_SUCCESS
COLOR_ACKED = COLOR_ACCENT
COLOR_TIMEOUT = COLOR_ERROR

STATUS_IDLE = "Idle"
STATUS_RUNNING = "Running"
STATUS_COMPLETE = "Complete"

SCENARIO_PRESETS = {
    "Low Errors": {
        "window_size": 4, "ber": 0.0001, "packet_loss": 0.01,
        "timeout_ms": 0, "num_packets": 10,
    },
    "Moderate Noise": {
        "window_size": 4, "ber": 0.001, "packet_loss": 0.03,
        "timeout_ms": 0, "num_packets": 10,
    },
    "High BER Nightmare": {
        "window_size": 4, "ber": 0.008, "packet_loss": 0.05,
        "timeout_ms": 0, "num_packets": 10,
    },
    "Packet Loss Hell": {
        "window_size": 4, "ber": 0.0005, "packet_loss": 0.20,
        "timeout_ms": 0, "num_packets": 10,
    },
}

DEFAULT_SCENARIO = "Low Errors"
