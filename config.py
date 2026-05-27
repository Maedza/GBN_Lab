"""
Go-Back-N Protocol Simulator — Configuration & Constants.
"""

# ---- Default Simulation Parameters ----
DEFAULT_WINDOW_SIZE = 4
DEFAULT_BER = 0.0001          # Bit error rate (0.0 – 1.0)
DEFAULT_PACKET_LOSS = 0.05    # Independent packet loss probability
DEFAULT_NUM_PACKETS = 10      # Total data packets to send
DEFAULT_TIMEOUT_MS = 300      # Timeout in milliseconds
DEFAULT_PACKET_SIZE_BITS = 1000
DEFAULT_DATA_RATE_KBPS = 100  # Channel data rate in kbps
DEFAULT_PROPAGATION_DELAY_MS = 10
DEFAULT_SIM_SPEED = 0.2       # Animation speed (0.1 = slow, 0.5 = readable, 1.0 = fast)

# ---- Simulation Engine ----
GUI_UPDATE_INTERVAL_MS = 50   # milliseconds between GUI polls
MAX_LOG_EVENTS = 80           # visible event log lines

# ---- Animation ----
ANIMATION_INTERVAL_MS = 80    # canvas redraw interval
PACKET_BOX_SIZE = 34          # size of each packet square on canvas
PACKET_SPACING = 6            # gap between packet squares

# ---- Color Scheme (dark theme) ----
COLOR_BG = "#0f172a"          # deepest background
COLOR_BG_PANEL = "#1e293b"   # panel / card background
COLOR_BG_HIGHLIGHT = "#334155"
COLOR_ACCENT = "#38bdf8"     # sky blue — primary accent
COLOR_BRAND = "#6366f1"      # indigo — secondary accent
COLOR_SUCCESS = "#4ade80"    # green
COLOR_ERROR = "#f87171"      # red
COLOR_WARNING = "#fbbf24"    # amber
COLOR_TEXT = "#f1f5f9"       # primary text
COLOR_TEXT_MUTED = "#94a3b8" # secondary text
COLOR_BORDER = "#334155"     # divider / border

# Packet state colours for the animation canvas
COLOR_UNSENT = "#334155"     # not yet sent
COLOR_SENT = COLOR_ACCENT    # sent, awaiting ACK
COLOR_ACKED = COLOR_SUCCESS  # acknowledged / delivered
COLOR_TIMEOUT = COLOR_ERROR  # timed out / corrupted

# ---- Status States ----
STATUS_IDLE = "Idle"
STATUS_RUNNING = "Running"
STATUS_COMPLETE = "Complete"

# ---- Scenario Presets ----
SCENARIO_PRESETS = {
    "Low Errors": {
        "window_size": 4, "ber": 0.0001, "packet_loss": 0.01,
        "timeout_ms": 300, "num_packets": 10,
    },
    "Moderate Noise": {
        "window_size": 4, "ber": 0.001, "packet_loss": 0.03,
        "timeout_ms": 300, "num_packets": 10,
    },
    "High BER Nightmare": {
        "window_size": 4, "ber": 0.008, "packet_loss": 0.05,
        "timeout_ms": 200, "num_packets": 10,
    },
    "Packet Loss Hell": {
        "window_size": 4, "ber": 0.0005, "packet_loss": 0.20,
        "timeout_ms": 250, "num_packets": 10,
    },
}

DEFAULT_SCENARIO = "Low Errors"
