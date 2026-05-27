"""
Go-Back-N Protocol Simulator — Configuration & Constants.
"""

# ---- Default Simulation Parameters ----
DEFAULT_WINDOW_SIZE = 4
DEFAULT_BER = 0.0001          # Bit error rate (0.0 – 1.0)
DEFAULT_PACKET_LOSS = 0.05    # Independent packet loss probability
DEFAULT_NUM_PACKETS = 10      # Total data packets to send
DEFAULT_TIMEOUT_MS = 0      # 0 = adaptive (3× RTT)
DEFAULT_PACKET_SIZE_BITS = 1000
DEFAULT_DATA_RATE_KBPS = 100  # Channel data rate in kbps
DEFAULT_PROPAGATION_DELAY_MS = 10
DEFAULT_SIM_SPEED = 0.2       # Animation speed (0.1 = slow, 0.5 = readable, 1.0 = fast)

# ---- Simulation Engine ----
GUI_UPDATE_INTERVAL_MS = 50   # milliseconds between GUI polls
MAX_LOG_EVENTS = 80           # visible event log lines

# ---- Animation ----
ANIMATION_INTERVAL_MS = 80    # canvas redraw interval
MONO_FONT = ("Consolas", "SF Mono", "Courier New", "TkFixedFont")
# cross-platform monospace — picks first available on each OS
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
        "timeout_ms": 0, "num_packets": 10,
        "description": (
            "Clean channel — bits rarely flip and packets seldom vanish. "
            "This is GBN at its happiest: the sender fills the window, "
            "ACKs stream back promptly, and all 10 packets arrive in order. "
            "The timer rarely fires here."
        ),
        "what_to_observe": (
            "Watch the pipeline run uninterrupted. "
            "Notice how cumulative ACKs slide the window forward "
            "without waiting for individual per-packet ACKs."
        ),
    },
    "Moderate Noise": {
        "window_size": 4, "ber": 0.001, "packet_loss": 0.03,
        "timeout_ms": 0, "num_packets": 10,
        "description": (
            "A realistic noisy channel. Roughly 1 in 1,000 bits gets "
            "corrupted, and a few packets (and their ACKs) drop entirely. "
            "The sender periodically hits timeouts and resends the window."
        ),
        "what_to_observe": (
            "Count how many retransmissions appear in the event log. "
            "Notice that a single lost packet forces the entire window "
            "to be resent — not just the missing one."
        ),
    },
    "High BER Nightmare": {
        "window_size": 4, "ber": 0.008, "packet_loss": 0.05,
        "timeout_ms": 0, "num_packets": 10,
        "description": (
            "Brutal bit-error rate. Nearly 1 in 125 bits is flipped — "
            "corruptions dominate the channel. Almost every round trip "
            "suffers a damaged packet or garbled ACK."
        ),
        "what_to_observe": (
            "Efficiency plummets here. The event log fills with "
            "CORRUPTED and TIMEOUT entries. Compare throughput with "
            "Low Errors — the drop is dramatic. Also, watch the "
            "animation canvas for red (timed-out) packet states."
        ),
    },
    "Packet Loss Hell": {
        "window_size": 4, "ber": 0.0005, "packet_loss": 0.20,
        "timeout_ms": 0, "num_packets": 10,
        "description": (
            "High packet loss — 1 in 5 packets simply disappears. "
            "Bit errors are rare; the problem is the channel silently "
            "swallowing packets (and their ACKs). GBN's window-based "
            "retransmission means every loss triggers a burst of re-sends."
        ),
        "what_to_observe": (
            "Look for 'LOST' and 'DISCARD' log entries. When a packet "
            "vanishes, the sender sends subsequent ones that the receiver "
            "throws away (out-of-order). After timeout, all in-flight "
            "packets get retransmitted at once."
        ),
    },
}

DEFAULT_SCENARIO = "Low Errors"
