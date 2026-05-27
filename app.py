"""
Go-Back-N Protocol Simulator — Single-file GUI.

Three-column layout:
  Left:   Controls (sliders + buttons)
  Center: Packet-flow animation canvas + event log
  Right:  Performance metrics

Minimal dependencies: customtkinter + tkinter canvas (no matplotlib).
"""

from __future__ import annotations

import time as _time
from collections import deque
from typing import Optional

import customtkinter as ctk
import tkinter as tk

from config import (
    DEFAULT_WINDOW_SIZE, DEFAULT_BER, DEFAULT_PACKET_LOSS, DEFAULT_NUM_PACKETS,
    DEFAULT_TIMEOUT_MS, DEFAULT_PACKET_SIZE_BITS, DEFAULT_DATA_RATE_KBPS,
    DEFAULT_PROPAGATION_DELAY_MS, DEFAULT_SIM_SPEED,
    GUI_UPDATE_INTERVAL_MS, ANIMATION_INTERVAL_MS,
    PACKET_BOX_SIZE, PACKET_SPACING, MAX_LOG_EVENTS,
    COLOR_BG, COLOR_BG_PANEL, COLOR_BG_HIGHLIGHT,
    COLOR_ACCENT, COLOR_SUCCESS, COLOR_ERROR, COLOR_WARNING,
    COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_BORDER,
    COLOR_UNSENT, COLOR_SENT, COLOR_ACKED, COLOR_TIMEOUT,
    STATUS_IDLE, STATUS_RUNNING, STATUS_COMPLETE,
    SCENARIO_PRESETS, DEFAULT_SCENARIO,
)
from simulation import GBNSimulation, EventType


# ═══════════════════════════════════════════════════════════════════════════════
# Theme setup
# ═══════════════════════════════════════════════════════════════════════════════

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ═══════════════════════════════════════════════════════════════════════════════
# Metric Card
# ═══════════════════════════════════════════════════════════════════════════════

class MetricCard(ctk.CTkFrame):
    """A single metric display: title + large value + unit."""

    def __init__(self, parent, title: str, unit: str = "", **kw):
        super().__init__(parent, fg_color=COLOR_BG_HIGHLIGHT, corner_radius=8, **kw)
        ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=11),
                     text_color=COLOR_TEXT_MUTED).pack(anchor="w", padx=12, pady=(8, 0))
        self._value = ctk.CTkLabel(self, text="--", font=ctk.CTkFont(size=24, weight="bold"),
                                    text_color=COLOR_ACCENT)
        self._value.pack(anchor="w", padx=12)
        if unit:
            ctk.CTkLabel(self, text=unit, font=ctk.CTkFont(size=9),
                         text_color=COLOR_TEXT_MUTED).pack(anchor="w", padx=12, pady=(0, 8))

    def set(self, text: str) -> None:
        self._value.configure(text=text)


# ═══════════════════════════════════════════════════════════════════════════════
# Main Application
# ═══════════════════════════════════════════════════════════════════════════════

class GBNLabApp(ctk.CTk):
    """Go-Back-N ARQ Protocol Simulator — main window."""

    def __init__(self):
        super().__init__()
        self.title("Go-Back-N Protocol Simulator")
        self.geometry("1280x760")
        self.minsize(1000, 640)
        self.configure(fg_color=COLOR_BG)

        # Simulation engine
        self._sim: Optional[GBNSimulation] = None
        self._state: dict = {}
        self._last_snapshot: dict = {}
        self._events: deque = deque(maxlen=MAX_LOG_EVENTS)

        # Polling handles
        self._poll_id: Optional[str] = None
        self._anim_id: Optional[str] = None
        self._anim_frame: int = 0
        self._anim_active: bool = False

        # Track completion
        self._completed = False

        # Replay system — two complementary recordings:
        #  _replay_events: per-event log (for the timeline seek bar + event log)
        #  _replay_frames: per-animation-tick visual state (for exact canvas playback)
        self._replay_events: list[dict] = []
        self._replay_frames: list[dict] = []            # animation-level recording
        self._replay_capturing: bool = False             # True during live simulation
        self._replay_mode: bool = False                  # True when showing replay UI
        self._replay_event_idx: int = 0                  # current event in seek bar
        self._replay_frame_idx: int = 0                  # current animation frame
        self._replay_playing: bool = False
        self._replay_id: Optional[str] = None

        # Flying packet animation state
        self._active_flights: dict[int, dict] = {}   # pkt_id -> {start_frame, direction, result, failed_at?}
        self._FLIGHT_FRAMES = 6                       # animation frames per flight hop
        self._FAIL_POINT = 0.65                       # where failed packets stop mid-flight
        self._FAIL_DISPLAY_FRAMES = 10                # frames to show X before removing

        # Feature flags
        self._step_mode = False
        self._step_paused = False
        self._neon = True
        self._sim_speed_replay = DEFAULT_SIM_SPEED  # stored for replay pacing

        self._build_ui()

        # Auto-load default scenario
        self._scenario_var.set(DEFAULT_SCENARIO)
        self._on_scenario_select(DEFAULT_SCENARIO)

        # Draw placeholder AFTER window is mapped (otherwise winfo_width hangs on macOS)
        self.after(100, self._draw_placeholder)

        # Force-quit guards
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind_all("<Command-q>", lambda e: self._force_quit())
        self.bind_all("<Control-q>", lambda e: self._force_quit())
        self.bind_all("<Command-w>", lambda e: self._on_close())

    # ══════════════════════════════════════════════════════════════════════════
    # Build UI
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        # ---- Title bar ----
        bar = ctk.CTkFrame(self, fg_color=COLOR_BG, height=44, corner_radius=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        ctk.CTkLabel(bar, text="Go-Back-N ARQ Protocol Simulator",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=COLOR_ACCENT).pack(side="left", padx=16, pady=10)

        self._status_dot = tk.Canvas(bar, width=14, height=14,
                                      bg=COLOR_BG, highlightthickness=0)
        self._status_dot.pack(side="right", padx=(0, 6), pady=10)
        self._dot = self._status_dot.create_oval(2, 2, 12, 12, fill="#475569", outline="")

        self._status_label = ctk.CTkLabel(bar, text="Idle", font=ctk.CTkFont(size=13),
                                           text_color=COLOR_TEXT_MUTED)
        self._status_label.pack(side="right", pady=10)

        # Separator
        ctk.CTkFrame(self, fg_color=COLOR_BORDER, height=1).pack(fill="x")

        # ---- Main content area ----
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)

        body.grid_columnconfigure(0, weight=0, minsize=240)
        body.grid_columnconfigure(1, weight=3)
        body.grid_columnconfigure(2, weight=0, minsize=240)
        body.grid_rowconfigure(0, weight=1)

        self._build_controls(body)
        self._build_center(body)
        self._build_metrics_panel(body)

    # ── Left: Controls ──────────────────────────────────────────────────────

    def _build_controls(self, parent) -> None:
        panel = ctk.CTkFrame(parent, fg_color=COLOR_BG_PANEL, corner_radius=0)
        panel.grid(row=0, column=0, sticky="ns")

        ctk.CTkLabel(panel, text="Parameters", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=COLOR_ACCENT).pack(padx=14, pady=(14, 4), anchor="w")

        # Scenario presets
        ctk.CTkLabel(panel, text="Scenario", font=ctk.CTkFont(size=11),
                     text_color=COLOR_TEXT_MUTED).pack(padx=14, pady=(6, 0), anchor="w")
        self._scenario_var = ctk.StringVar(value="Custom")
        scenario_names = ["Custom"] + list(SCENARIO_PRESETS.keys())
        self._scenario_menu = ctk.CTkOptionMenu(
            panel, values=scenario_names, variable=self._scenario_var,
            command=self._on_scenario_select,
            fg_color=COLOR_BG_HIGHLIGHT, button_color=COLOR_ACCENT,
            text_color=COLOR_TEXT, dropdown_fg_color=COLOR_BG_PANEL,
            font=ctk.CTkFont(size=11), width=210,
        )
        self._scenario_menu.pack(padx=14, pady=(2, 8))

        self._window_slider, self._window_val = self._slider(
            panel, "Window Size (N)", DEFAULT_WINDOW_SIZE, 1, 10, 1)
        self._ber_slider, self._ber_val = self._slider(
            panel, "Bit Error Rate", DEFAULT_BER, 0.0, 0.01, 0.0001)
        self._loss_slider, self._loss_val = self._slider(
            panel, "Packet Loss", DEFAULT_PACKET_LOSS, 0.0, 0.5, 0.01)
        self._timeout_slider, self._timeout_val = self._slider(
            panel, "Timeout (ms)", DEFAULT_TIMEOUT_MS, 100, 2000, 50)
        self._packets_slider, self._packets_val = self._slider(
            panel, "Packets to Send", DEFAULT_NUM_PACKETS, 1, 20, 1)
        self._speed_slider, self._speed_val = self._slider(
            panel, "Simulation Speed", DEFAULT_SIM_SPEED, 0.1, 2.0, 0.1)
        # Fix speed display to show 1 decimal
        self._speed_slider.configure(
            command=lambda v: self._speed_val.configure(text=f"{float(v):.1f}x"))

        # Info about what each parameter does
        info = (
            "GBN sends up to N packets\n"
            "without waiting for ACKs.\n"
            "On timeout, retransmits\n"
            "the entire window."
        )
        ctk.CTkLabel(panel, text=info, font=ctk.CTkFont(size=10),
                     text_color=COLOR_TEXT_MUTED, justify="left",
                     wraplength=200).pack(padx=14, pady=(20, 10), anchor="w")

        # ── Step-by-step mode toggle ──
        self._step_mode_var = ctk.BooleanVar(value=False)
        self._step_switch = ctk.CTkSwitch(
            panel, text="Step-by-Step Mode", variable=self._step_mode_var,
            command=self._on_step_mode_toggle,
            font=ctk.CTkFont(size=11),
            progress_color=COLOR_ACCENT, button_color=COLOR_TEXT,
            text_color=COLOR_TEXT_MUTED,
        )
        self._step_switch.pack(padx=14, pady=(0, 2), anchor="w")

        ctk.CTkLabel(panel, text="Pause after each event with explanations",
                     font=ctk.CTkFont(size=9),
                     text_color=COLOR_TEXT_MUTED, justify="left",
                     ).pack(padx=28, pady=(0, 6), anchor="w")

        # ── Neon glow mode toggle ──
        self._neon_var = ctk.BooleanVar(value=True)
        self._neon_switch = ctk.CTkSwitch(
            panel, text="Neon Glow Mode", variable=self._neon_var,
            command=self._on_neon_toggle,
            font=ctk.CTkFont(size=11),
            progress_color=COLOR_WARNING, button_color=COLOR_TEXT,
            text_color=COLOR_TEXT_MUTED,
        )
        self._neon_switch.pack(padx=14, pady=(0, 2), anchor="w")

        ctk.CTkLabel(panel, text="Glowing packet effects for demos",
                     font=ctk.CTkFont(size=9),
                     text_color=COLOR_TEXT_MUTED, justify="left",
                     ).pack(padx=28, pady=(0, 6), anchor="w")

        # Buttons
        btn_opts = {"width": 210, "height": 36, "font": ctk.CTkFont(size=13, weight="bold")}

        self._start_btn = ctk.CTkButton(
            panel, text="Start Simulation", fg_color="#166534",
            hover_color="#14532d", command=self._on_start, **btn_opts)
        self._start_btn.pack(padx=14, pady=(10, 6))

        self._stop_btn = ctk.CTkButton(
            panel, text="Reset", fg_color="#475569", hover_color="#334155",
            command=self._on_reset, **btn_opts)
        self._stop_btn.pack(padx=14, pady=(0, 4))

        # ── Save / Load / Export ──
        ctk.CTkLabel(panel, text="Data", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=COLOR_TEXT_MUTED).pack(padx=14, pady=(12, 4), anchor="w")

        row1 = ctk.CTkFrame(panel, fg_color="transparent")
        row1.pack(fill="x", padx=14, pady=(0, 3))
        ctk.CTkButton(row1, text="Save .gbn", width=100, height=28,
                      font=ctk.CTkFont(size=11), fg_color="#334155",
                      hover_color="#475569", command=self._on_save).pack(side="left", padx=(0, 4))
        ctk.CTkButton(row1, text="Load .gbn", width=100, height=28,
                      font=ctk.CTkFont(size=11), fg_color="#334155",
                      hover_color="#475569", command=self._on_load).pack(side="left")

        ctk.CTkButton(panel, text="Export GIF", width=210, height=28,
                      font=ctk.CTkFont(size=11), fg_color="#6366f1",
                      hover_color="#4f46e5", command=self._on_export_gif).pack(padx=14, pady=(4, 0))

        self._load_saved_state: Optional[dict] = None

    def _slider(self, parent, label: str, default: float, lo: float, hi: float,
                step: float) -> tuple[ctk.CTkSlider, ctk.CTkLabel]:
        ctk.CTkLabel(parent, text=label, font=ctk.CTkFont(size=11),
                     text_color=COLOR_TEXT_MUTED).pack(padx=14, pady=(12, 0), anchor="w")

        row = ctk.CTkFrame(parent, fg_color="transparent", height=30)
        row.pack(fill="x", padx=14, pady=(2, 0))
        row.pack_propagate(False)

        val_lbl = ctk.CTkLabel(row, text=str(default), width=50,
                                font=ctk.CTkFont(size=11), text_color=COLOR_TEXT)
        val_lbl.pack(side="right")

        var = ctk.DoubleVar(value=default)
        s = ctk.CTkSlider(row, from_=lo, to=hi,
                          number_of_steps=int((hi - lo) / step),
                          variable=var,
                          command=lambda v: val_lbl.configure(
                              text=f"{float(v):.4f}" if isinstance(step, float) and step < 1
                              else str(int(float(v)))),
                          progress_color=COLOR_ACCENT, button_color=COLOR_ACCENT,
                          height=14)
        s.pack(side="left", fill="x", expand=True, padx=(0, 8))
        return s, val_lbl

    # ── Center: Animation + Event Log ───────────────────────────────────────

    def _build_center(self, parent) -> None:
        center = ctk.CTkFrame(parent, fg_color="transparent")
        center.grid(row=0, column=1, sticky="nsew", padx=(6, 6))
        center.grid_rowconfigure(0, weight=3)
        center.grid_rowconfigure(1, weight=0, minsize=36)  # timeline scrubber
        center.grid_rowconfigure(2, weight=1)  # event log
        center.grid_columnconfigure(0, weight=1)

        # Canvas
        self._canvas = tk.Canvas(center, bg=COLOR_BG, highlightthickness=0)
        self._canvas.grid(row=0, column=0, sticky="nsew", pady=(0, 2))

        # ── Progress / Replay bar (dual-purpose) ──
        scrub_frame = ctk.CTkFrame(center, fg_color=COLOR_BG_PANEL, corner_radius=6,
                                   height=36)
        scrub_frame.grid(row=1, column=0, sticky="ew", pady=(0, 2))
        scrub_frame.pack_propagate(False)
        scrub_frame.grid_propagate(False)

        # ── Sim progress sub-frame (shown during sim) ──
        self._sim_progress_frame = ctk.CTkFrame(scrub_frame, fg_color="transparent",
                                                 height=34)
        self._sim_progress_frame.pack(fill="x", expand=True)

        self._progress_label = ctk.CTkLabel(
            self._sim_progress_frame, text="Progress: --/--",
            font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED,
        )
        self._progress_label.pack(side="left", padx=(12, 0))

        # ── Replay control sub-frame (shown after completion) ──
        self._replay_frame = ctk.CTkFrame(scrub_frame, fg_color="transparent",
                                          height=34)

        self._replay_slider_var = ctk.IntVar(value=0)
        self._replay_slider = ctk.CTkSlider(
            self._replay_frame, from_=0, to=1, variable=self._replay_slider_var,
            command=self._on_replay_seek,
            progress_color=COLOR_ACCENT, button_color=COLOR_ACCENT, height=14,
        )
        self._replay_slider.pack(side="left", fill="x", expand=True, padx=(8, 6))

        self._replay_step_back_btn = ctk.CTkButton(
            self._replay_frame, text="◀", width=28, height=26,
            fg_color=COLOR_BG_HIGHLIGHT, hover_color=COLOR_BORDER,
            command=self._on_replay_step_back, font=ctk.CTkFont(size=11),
        )
        self._replay_step_back_btn.pack(side="left", padx=1)

        self._replay_play_btn = ctk.CTkButton(
            self._replay_frame, text="▶", width=34, height=26,
            fg_color=COLOR_ACCENT, hover_color="#4f46e5",
            command=self._on_replay_play, font=ctk.CTkFont(size=11),
        )
        self._replay_play_btn.pack(side="left", padx=1)

        self._replay_step_fwd_btn = ctk.CTkButton(
            self._replay_frame, text="▶", width=28, height=26,
            fg_color=COLOR_BG_HIGHLIGHT, hover_color=COLOR_BORDER,
            command=self._on_replay_step_fwd, font=ctk.CTkFont(size=11),
        )
        self._replay_step_fwd_btn.pack(side="left", padx=1)

        self._replay_pos_label = ctk.CTkLabel(
            self._replay_frame, text="  0/0", font=ctk.CTkFont(size=10),
            text_color=COLOR_TEXT_MUTED, width=380, anchor="w",
        )
        self._replay_pos_label.pack(side="right", padx=(0, 8), fill="x", expand=True)

        # Event log
        log_frame = ctk.CTkFrame(center, fg_color=COLOR_BG_PANEL, corner_radius=8)
        log_frame.grid(row=2, column=0, sticky="nsew")
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(log_frame, fg_color="transparent", height=26)
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 0))
        ctk.CTkLabel(header, text="Event Log", font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=COLOR_TEXT_MUTED).pack(side="left")

        self._log_text = tk.Text(log_frame, bg="#0f172a", fg=COLOR_TEXT,
                                  font=("SF Mono", 11), wrap="word",
                                  bd=0, padx=8, pady=4,
                                  insertbackground=COLOR_ACCENT,
                                  highlightthickness=0, state="disabled")
        self._log_text.grid(row=1, column=0, sticky="nsew", padx=6, pady=(2, 6))

        # Color tags
        self._log_text.tag_configure("ok", foreground=COLOR_SUCCESS)
        self._log_text.tag_configure("err", foreground=COLOR_ERROR)
        self._log_text.tag_configure("warn", foreground=COLOR_WARNING)
        self._log_text.tag_configure("info", foreground=COLOR_ACCENT)
        self._log_text.tag_configure("ts", foreground=COLOR_TEXT_MUTED,
                                      font=("SF Mono", 10))

    # ── Right: Metrics ──────────────────────────────────────────────────────

    def _build_metrics_panel(self, parent) -> None:
        panel = ctk.CTkFrame(parent, fg_color=COLOR_BG_PANEL, corner_radius=0)
        panel.grid(row=0, column=2, sticky="ns")

        ctk.CTkLabel(panel, text="Performance", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=COLOR_ACCENT).pack(padx=14, pady=(14, 8), anchor="w")

        self._cards: dict[str, MetricCard] = {}
        specs = [
            ("throughput", "Throughput", "kbps"),
            ("efficiency", "Efficiency", "%"),
            ("retransmissions", "Retransmissions", "packets"),
            ("timeouts", "Timeouts", "events"),
            ("delay", "Avg Delay", "ms"),
        ]
        for key, title, unit in specs:
            self._cards[key] = MetricCard(panel, title, unit)
            self._cards[key].pack(fill="x", padx=10, pady=(0, 6))

        # Event counts
        ctk.CTkLabel(panel, text="Channel Stats", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=COLOR_TEXT_MUTED).pack(padx=14, pady=(14, 4), anchor="w")
        self._chan_label = ctk.CTkLabel(panel, text="Lost: --  Corrupted: --",
                                         font=ctk.CTkFont(size=12),
                                         text_color=COLOR_TEXT_MUTED)
        self._chan_label.pack(padx=14, anchor="w")

    # ══════════════════════════════════════════════════════════════════════════
    # Status
    # ══════════════════════════════════════════════════════════════════════════

    _STATUS_COLORS = {
        STATUS_IDLE: "#475569",
        STATUS_RUNNING: COLOR_SUCCESS,
        STATUS_COMPLETE: COLOR_ACCENT,
    }

    def _set_status(self, status: str) -> None:
        color = self._STATUS_COLORS.get(status, "#475569")
        self._status_dot.itemconfig(self._dot, fill=color)
        self._status_label.configure(text=status, text_color=color)

    # ══════════════════════════════════════════════════════════════════════════
    # Event Handlers
    # ══════════════════════════════════════════════════════════════════════════

    def _on_scenario_select(self, name: str) -> None:
        """Load a preset scenario's parameters into the sliders.

        sim_speed is intentionally NOT set by scenarios — it is a visual
        preference controlled by DEFAULT_SIM_SPEED in config.py and adjusted
        by the user.  Changing a scenario should not change playback speed.
        """
        if name == "Custom":
            return
        preset = SCENARIO_PRESETS.get(name)
        if not preset:
            return
        self._window_slider.set(preset["window_size"])
        self._ber_slider.set(preset["ber"])
        self._loss_slider.set(preset["packet_loss"])
        self._timeout_slider.set(preset["timeout_ms"])
        self._packets_slider.set(preset["num_packets"])
        # Update display labels
        self._window_val.configure(text=str(preset["window_size"]))
        self._ber_val.configure(text=f"{preset['ber']:.4f}")
        self._loss_val.configure(text=f"{preset['packet_loss']:.2f}")
        self._timeout_val.configure(text=str(preset["timeout_ms"]))
        self._packets_val.configure(text=str(preset["num_packets"]))

    def _on_step_mode_toggle(self) -> None:
        self._step_mode = self._step_mode_var.get()

    def _on_neon_toggle(self) -> None:
        self._neon = self._neon_var.get()
        self._redraw_canvas()

    def _on_start(self) -> None:
        self._reset_ui()

        window_size = int(self._window_slider.get())
        ber = round(self._ber_slider.get(), 4)
        packet_loss = round(self._loss_slider.get(), 4)
        timeout_ms = int(self._timeout_slider.get())
        num_packets = int(self._packets_slider.get())
        sim_speed = round(self._speed_slider.get(), 1)

        self._sim = GBNSimulation(
            window_size=window_size,
            ber=ber,
            packet_loss=packet_loss,
            timeout_ms=timeout_ms,
            num_packets=num_packets,
            packet_size_bits=DEFAULT_PACKET_SIZE_BITS,
            data_rate_kbps=DEFAULT_DATA_RATE_KBPS,
            propagation_delay_ms=DEFAULT_PROPAGATION_DELAY_MS,
            sim_speed=sim_speed,
        )

        self._sim_speed_replay = sim_speed  # store for replay pacing

        # Log initial info BEFORE starting the sim so it appears first
        self._log("info", f"Go-Back-N |  N={window_size}  BER={ber:.4f}  "
                  f"loss={packet_loss:.0%}  pkts={num_packets}  timeout={timeout_ms}ms")

        self._sim.start()
        self._set_status(STATUS_RUNNING)

        if self._step_mode:
            self._start_btn.configure(text="Running (Step)...", fg_color="#475569", state="disabled")
            self._step_paused = False
        else:
            self._start_btn.configure(text="Running...", fg_color="#475569", state="disabled")

        self._completed = False

        # Begin recording animation frames for replay
        self._replay_capturing = True
        self._replay_frames.clear()
        self._replay_events.clear()

        # Start polling
        self._start_polling()

        # Start animation (only during simulation)
        self._start_animation()

    # ── Save / Load / Export ─────────────────────────────────────────────────

    def _on_save(self) -> None:
        """Save current config + event history as .gbn file."""
        from tkinter import filedialog
        from persistence import save_gbn

        config = {
            "window_size": int(self._window_slider.get()),
            "ber": round(self._ber_slider.get(), 4),
            "packet_loss": round(self._loss_slider.get(), 4),
            "timeout_ms": int(self._timeout_slider.get()),
            "num_packets": int(self._packets_slider.get()),
            "sim_speed": round(self._speed_slider.get(), 1),
        }
        # Serialise event log
        log_text = self._log_text.get("1.0", "end-1c")
        events = [{"line": line} for line in log_text.split("\n") if line.strip()]

        path = filedialog.asksaveasfilename(
            defaultextension=".gbn",
            filetypes=[("GBN State Files", "*.gbn"), ("All Files", "*.*")],
            title="Save Simulation State",
        )
        if path:
            save_gbn(path, config, events)
            self._log("info", f"State saved to {path}")

    def _on_load(self) -> None:
        """Load a .gbn file and populate the parameter sliders."""
        from tkinter import filedialog
        from persistence import load_gbn

        path = filedialog.askopenfilename(
            filetypes=[("GBN State Files", "*.gbn"), ("All Files", "*.*")],
            title="Load Simulation State",
        )
        if not path:
            return

        data = load_gbn(path)
        if not data:
            self._log("err", f"Failed to load {path} — invalid .gbn file")
            return

        cfg = data["config"]
        self._window_slider.set(cfg.get("window_size", 4))
        self._ber_slider.set(cfg.get("ber", 0.0001))
        self._loss_slider.set(cfg.get("packet_loss", 0.05))
        self._timeout_slider.set(cfg.get("timeout_ms", 300))
        self._packets_slider.set(cfg.get("num_packets", 10))
        self._speed_slider.set(cfg.get("sim_speed", 0.3))
        # Update labels
        self._window_val.configure(text=str(cfg.get("window_size", 4)))
        self._ber_val.configure(text=f"{cfg.get('ber', 0.0001):.4f}")
        self._loss_val.configure(text=f"{cfg.get('packet_loss', 0.05):.2f}")
        self._timeout_val.configure(text=str(cfg.get("timeout_ms", 300)))
        self._packets_val.configure(text=str(cfg.get("num_packets", 10)))
        self._speed_val.configure(text=f"{cfg.get('sim_speed', 0.3):.1f}x")

        # Reset scenario dropdown to "Custom" since we loaded custom params
        self._scenario_var.set("Custom")

        # Restore event log
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        for event in data.get("events", []):
            line = event.get("line", "")
            self._log_text.insert("end", line + "\n")
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

        self._log("info", f"Loaded state from {path}")
        self._load_saved_state = data

    def _on_export_gif(self) -> None:
        """Export current canvas as an animated GIF."""
        from tkinter import filedialog
        from persistence import export_gif

        path = filedialog.asksaveasfilename(
            defaultextension=".gif",
            filetypes=[("Animated GIF", "*.gif"), ("All Files", "*.*")],
            title="Export Animation as GIF",
        )
        if not path:
            return

        self._log("info", "Exporting GIF — capturing frames...")
        self.update()  # force canvas redraw

        # Capture current canvas
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()

        success = export_gif(self._canvas, path, width=w, height=h,
                             num_frames=20, delay_ms=120)
        if success:
            self._log("ok", f"GIF exported to {path}")
        else:
            self._log("err", "GIF export failed")

    def _on_reset(self) -> None:
        if self._sim:
            self._sim.stop()
            self._sim = None
        self._stop_polling()
        self._stop_animation()
        self._destroy_step_frame()
        self._reset_ui()
        self._set_status(STATUS_IDLE)
        self._start_btn.configure(text="Start Simulation", fg_color="#166534",
                                  state="normal")

    def _reset_ui(self) -> None:
        for card in self._cards.values():
            card.set("--")
        self._chan_label.configure(text="Lost: --  Corrupted: --")
        self._update_progress(0, 0)
        # Hide replay controls if visible
        self._stop_replay_auto()
        self._replay_mode = False
        self._replay_frame.pack_forget()
        self._sim_progress_frame.pack(fill="x", expand=True)
        # Keep log history across runs — add a separator if there was content
        log_already_has_content = self._log_text.get("1.0", "end-1c").strip() != ""
        self._log_text.configure(state="normal")
        if log_already_has_content:
            self._log_text.insert("end", "\n" + "─" * 50 + " NEW RUN " + "─" * 50 + "\n\n", "info")
        self._log_text.configure(state="disabled")
        self._events.clear()
        self._replay_events.clear()
        self._replay_frames.clear()
        self._replay_capturing = False
        self._replay_mode = False
        self._replay_playing = False
        self._replay_event_idx = 0
        self._replay_frame_idx = 0
        self._state = {}
        self._last_snapshot = {}
        self._active_flights.clear()
        self._canvas.delete("all")
        self._draw_placeholder()

    # ══════════════════════════════════════════════════════════════════════════
    # Polling
    # ══════════════════════════════════════════════════════════════════════════

    def _start_polling(self) -> None:
        if self._poll_id:
            self.after_cancel(self._poll_id)
        # Drain any messages that arrived between sim.start() and now
        self._poll()
        if self._sim and self._sim.running:
            self._poll_id = self.after(GUI_UPDATE_INTERVAL_MS, self._poll)

    def _stop_polling(self) -> None:
        if self._poll_id:
            self.after_cancel(self._poll_id)
            self._poll_id = None

    def _poll(self) -> None:
        if self._sim is None:
            return

        if self._step_mode and self._step_paused:
            # Don't poll when paused in step mode
            self._poll_id = self.after(GUI_UPDATE_INTERVAL_MS, self._poll)
            return

        for msg in self._sim.poll():
            t = msg["type"]
            if t == "event":
                # Update snapshot BEFORE _on_event so _dump_window sees current state
                self._last_snapshot = msg.get("state_snapshot", {})
                # Process the event FIRST so flights are in sync with the event
                self._on_event(msg["event"])
                # Capture event for the replay timeline seek bar
                # (visual state is captured separately in _schedule_animation)
                evt = msg["event"]
                self._replay_events.append({
                    "event_type": evt.type,
                    "event_time": evt.time,
                    "event_packet_id": evt.packet_id,
                    "event_ack_id": evt.ack_id,
                    "event_meta": dict(getattr(evt, "meta", {}) or {}),
                    # Record where we are in the animation recording for seek mapping
                    "anim_frame": self._anim_frame,
                })

                # Pause in step mode after each event
                if self._step_mode:
                    self._step_paused = True
                    self._pause_for_step(msg["event"])
                    return  # stop processing for now

            elif t == "tick":
                self._last_snapshot = msg.get("state_snapshot", {})
            elif t == "done":
                self._destroy_step_frame()
                self._on_done(msg.get("metrics", {}))
                return  # _on_done sets _sim = None, stop polling

        # Guard: _on_done may have cleared _sim
        if self._sim is None:
            return

        if self._sim.running:
            self._poll_id = self.after(GUI_UPDATE_INTERVAL_MS, self._poll)
        elif not self._completed:
            if self._sim.delivered >= self._sim.num_packets:
                self._destroy_step_frame()
                self._on_done(self._sim.metrics)

    # ── Step-by-step helpers ────────────────────────────────────────────────

    _EXPLANATIONS = {
        EventType.PACKET_SENT:
            "The sender transmits this packet. GBN allows up to N\n"
            "packets in flight without waiting for individual ACKs.\n"
            "A single timer tracks the oldest unACKed packet.",
        EventType.PACKET_RECEIVED:
            "The receiver gets this packet. If it's the next expected\n"
            "one, it's accepted and a cumulative ACK is sent.\n"
            "The ACK means 'I've received everything up to this point.'",
        EventType.PACKET_CORRUPTED:
            "Bit errors from the noisy channel corrupted this packet.\n"
            "The receiver detects the error and discards it.\n"
            "A duplicate ACK may be sent to signal the sender.",
        EventType.PACKET_LOST:
            "The packet was lost entirely — never reached the receiver.\n"
            "GBN relies on timeouts to detect losses.\n"
            "When the timer fires, the entire window is retransmitted.",
        EventType.ACK_SENT:
            "The receiver sends back a cumulative ACK.\n"
            "In GBN, ACK(N) acknowledges ALL packets up to N.\n"
            "This is more efficient than individual ACKs.",
        EventType.ACK_RECEIVED:
            "The sender receives the cumulative ACK.\n"
            "The window slides forward — new packets can now be sent.\n"
            "The timer is reset for the new oldest unACKed packet.",
        EventType.ACK_CORRUPTED:
            "The ACK was corrupted by channel noise.\n"
            "The sender ignores corrupted ACKs.\n"
            "Eventually, the timer will fire and trigger retransmission.",
        EventType.ACK_LOST:
            "The ACK was lost in transmission.\n"
            "From the sender's perspective, this is identical to\n"
            "a corrupted ACK — the timer will handle recovery.",
        EventType.TIMEOUT:
            "The timer for the oldest unACKed packet expired.\n"
            "This is GBN's key mechanism: the entire window from\n"
            "base to next_seq-1 is retransmitted. All packets\n"
            "arriving out of order at the receiver are discarded.",
    }

    def _destroy_step_frame(self) -> None:
        """Remove the floating step-control overlay if it exists."""
        if hasattr(self, "_step_frame") and self._step_frame.winfo_exists():
            self._step_frame.destroy()

    def _pause_for_step(self, event) -> None:
        """Pause simulation and show a clear overlay with explanation + controls."""
        self._step_paused = True
        self._set_status("Step — Paused")
        self._status_label.configure(text_color=COLOR_WARNING)

        # Destroy any previous overlay
        self._destroy_step_frame()

        # Build fresh overlay so we never have stale widget-parent issues
        self._step_frame = ctk.CTkFrame(self, fg_color=COLOR_BG_PANEL, corner_radius=10,
                                        border_width=2, border_color=COLOR_WARNING)
        self._step_frame.place(relx=0.5, rely=0.90, anchor="s")

        # Title
        ctk.CTkLabel(
            self._step_frame, text=f"▶ STEP PAUSED — {event.type}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR_WARNING,
        ).pack(padx=16, pady=(10, 2))

        # Explanation
        explanation = self._EXPLANATIONS.get(event.type, "No explanation available.")
        ctk.CTkLabel(
            self._step_frame, text=explanation,
            font=ctk.CTkFont(size=11), text_color=COLOR_TEXT,
            justify="left", wraplength=420,
        ).pack(padx=16, pady=(2, 8))

        # Buttons
        btn_row = ctk.CTkFrame(self._step_frame, fg_color="transparent")
        btn_row.pack(padx=16, pady=(0, 10))
        ctk.CTkButton(
            btn_row, text="▶  Next Step", fg_color="#6366f1",
            hover_color="#4f46e5", command=self._on_step_continue,
            font=ctk.CTkFont(size=12, weight="bold"), width=130, height=34,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_row, text="⏩  Run to End", fg_color="#475569",
            hover_color="#334155", command=self._on_step_run_to_end,
            font=ctk.CTkFont(size=12), width=130, height=34,
        ).pack(side="left", padx=4)

        self._log("warn", f"STEP PAUSED — {event.type}")

    def _on_step_continue(self) -> None:
        """Resume from step pause for one more event."""
        self._step_paused = False
        self._destroy_step_frame()
        self._set_status(STATUS_RUNNING)
        self._status_label.configure(text_color=COLOR_SUCCESS)
        self._start_polling()

    def _on_step_run_to_end(self) -> None:
        """Disable step mode and run to completion."""
        self._step_mode = False
        self._step_paused = False
        self._step_mode_var.set(False)
        self._destroy_step_frame()
        self._set_status(STATUS_RUNNING)
        self._status_label.configure(text_color=COLOR_SUCCESS)
        self._log("info", "Step mode disabled — running to completion...")
        self._start_polling()

    def _update_progress(self, delivered: int = -1, total: int = -1) -> None:
        """Update sim progress label. Call with no args to reset."""
        if delivered < 0 or total <= 0:
            self._progress_label.configure(text="Progress: --/--")
        else:
            self._progress_label.configure(text=f"Progress: {delivered}/{total} packets")

    # ── Replay controls ────────────────────────────────────────────────────
    #
    # Two layers work together:
    #   1. _replay_frames:  per-animation-tick canvas recordings (the visuals)
    #   2. _replay_events:  per-event log entries (the timeline seek bar)
    #
    # During auto-play, the animation loop loads one recorded frame per tick.
    # The event log / seek bar position advance whenever the current animation
    # frame passes the next event's recorded anim_frame.
    #
    # Seeking maps event index → closest animation frame index.

    def _show_replay_controls(self) -> None:
        """Switch to replay mode: hide sim progress, show seek + play controls."""
        self._replay_mode = True
        self._sim_progress_frame.pack_forget()
        n_events = max(len(self._replay_events), 1)
        self._replay_slider.configure(to=n_events - 1, number_of_steps=n_events)
        last = n_events - 1
        self._replay_slider_var.set(last)
        self._replay_pos_label.configure(text=f"  {last}/{last}")
        self._replay_frame.pack(fill="x", expand=True)
        # Clear log and start fresh for replay mirror
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")
        # Reset animation clock so recorded flight start_frame values line up
        self._anim_frame = 0
        # Show the final frame (last event → last animation frame)
        self._seek_to_event(last)

    # ── Map event index ↔ animation frame index ──────────────────────

    def _event_to_frame_idx(self, event_idx: int) -> int:
        """Find the animation frame closest to the given event's recorded time."""
        events = self._replay_events
        frames = self._replay_frames
        if not events or not frames:
            return 0
        target = events[max(0, min(event_idx, len(events) - 1))]["anim_frame"]
        # Find the last animation frame with anim_frame ≤ target
        best = 0
        for i, f in enumerate(frames):
            if f.get("anim_frame", i) <= target:
                best = i
            else:
                break
        return best

    def _frame_to_event_idx(self, frame_idx: int) -> int:
        """Find the event whose anim_frame is closest to this animation frame."""
        events = self._replay_events
        frames = self._replay_frames
        if not events or not frames:
            return 0
        if frame_idx >= len(frames):
            frame_idx = len(frames) - 1
        current = frames[frame_idx].get("anim_frame", frame_idx)
        best = 0
        for i, ev in enumerate(events):
            if ev["anim_frame"] <= current:
                best = i
            else:
                break
        return best

    # ── Seek bar / stepping ──────────────────────────────────────────

    def _seek_to_event(self, event_idx: int) -> None:
        """Jump to the given event: load its snapshot + rebuild event log."""
        n_events = len(self._replay_events)
        if n_events == 0:
            return
        event_idx = max(0, min(event_idx, n_events - 1))
        self._replay_event_idx = event_idx
        self._replay_slider_var.set(event_idx)

        frame_idx = self._event_to_frame_idx(event_idx)
        self._replay_frame_idx = frame_idx

        if self._replay_frames:
            f = self._replay_frames[min(frame_idx, len(self._replay_frames) - 1)]
            self._last_snapshot = f["snapshot"]
            # Clone flights so rendering uses current _anim_frame for progress
            self._active_flights.clear()
            for fid, fdata in f["flights"].items():
                self._active_flights[fid] = dict(fdata)
            # Shift flight start times to sync with current _anim_frame
            # so they look like they just started (seek loads a still frame)
            frame_anim = f.get("anim_frame", frame_idx)
            for flight in self._active_flights.values():
                flight["start_frame"] = self._anim_frame - (frame_anim - flight.get("start_frame", 0))

        self._redraw_canvas()

        # Rebuild event log up to and including this event
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        for i in range(event_idx + 1):
            self._log_replay_event(self._replay_events[i])
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

        # Label
        ev = self._replay_events[event_idx]
        desc = self._describe_replay_event(
            ev["event_type"], ev.get("event_packet_id", -1),
            ev.get("event_ack_id", -1), ev.get("event_time", 0))
        self._replay_pos_label.configure(text=f"  {event_idx}/{n_events - 1}  {desc}")

    def _on_replay_seek(self, value: float) -> None:
        if self._replay_playing:
            self._stop_replay_auto()
        self._seek_to_event(int(round(float(value))))

    def _on_replay_step_back(self) -> None:
        if self._replay_playing:
            self._stop_replay_auto()
        if self._replay_event_idx > 0:
            self._seek_to_event(self._replay_event_idx - 1)

    def _on_replay_step_fwd(self) -> None:
        if self._replay_playing:
            self._stop_replay_auto()
        n = len(self._replay_events)
        if n > 0 and self._replay_event_idx < n - 1:
            self._seek_to_event(self._replay_event_idx + 1)

    # ── Auto-play ─────────────────────────────────────────────────────

    def _on_replay_play(self) -> None:
        if self._replay_playing:
            self._stop_replay_auto()
        else:
            self._start_replay_auto()

    def _start_replay_auto(self) -> None:
        """Begin playing back recorded animation frames."""
        self._replay_playing = True
        self._replay_play_btn.configure(text="⏸", fg_color=COLOR_WARNING,
                                         hover_color="#ca8a04")
        # Start the shared animation loop — it switches to playback mode
        self._start_animation()

    def _stop_replay_auto(self) -> None:
        """Stop playback, leave canvas at current state."""
        self._replay_playing = False
        self._stop_animation()
        self._replay_play_btn.configure(text="▶", fg_color=COLOR_ACCENT,
                                         hover_color="#4f46e5")

    def _playback_animation_frame(self) -> None:
        """Load the next pre-recorded animation frame and redraw.
        
        Called from _schedule_animation() when _replay_mode is True.
        Plays frames at the same ANIMATION_INTERVAL_MS rate they were recorded at,
        guaranteeing identical visual output to the live simulation.
        
        Flight start_frame values from the recording are adjusted to sync with
        the playback _anim_frame so elapsed time (and thus flight positions) match.
        """
        frames = self._replay_frames
        if not frames:
            return

        if self._replay_playing:
            # Auto-advance
            if self._replay_frame_idx < len(frames) - 1:
                self._replay_frame_idx += 1
            else:
                self._stop_replay_auto()
                return

        idx = min(self._replay_frame_idx, len(frames) - 1)
        f = frames[idx]
        self._last_snapshot = f["snapshot"]

        # Map recorded flight start times to playback timeline
        recorded_anim = f["anim_frame"]
        self._active_flights.clear()
        for fid, fdata in f["flights"].items():
            fc = dict(fdata)
            # Adjust: we want elapsed = recorded_anim - original_start
            # In playback: elapsed = _anim_frame - new_start
            # So: new_start = _anim_frame - (recorded_anim - original_start)
            original_start = fc.get("start_frame", recorded_anim)
            fc["start_frame"] = self._anim_frame - (recorded_anim - original_start)
            self._active_flights[fid] = fc

        self._redraw_canvas()

        # Update event log and seek bar to match current animation frame
        ev_idx = self._frame_to_event_idx(idx)
        if ev_idx != self._replay_event_idx:
            self._replay_event_idx = ev_idx
            self._replay_slider_var.set(ev_idx)
            self._log_text.configure(state="normal")
            self._log_text.delete("1.0", "end")
            for i in range(ev_idx + 1):
                self._log_replay_event(self._replay_events[i])
            self._log_text.see("end")
            self._log_text.configure(state="disabled")
            ev = self._replay_events[ev_idx]
            desc = self._describe_replay_event(
                ev["event_type"], ev.get("event_packet_id", -1),
                ev.get("event_ack_id", -1), ev.get("event_time", 0))
            n_events = len(self._replay_events)
            self._replay_pos_label.configure(text=f"  {ev_idx}/{n_events - 1}  {desc}")

    def _log_replay_event(self, event: dict) -> None:
        """Log a replay event to the event log mirroring live-sim format."""
        etype = event["event_type"]
        pid = event.get("event_packet_id", -1)
        ack = event.get("event_ack_id", -1)
        t = event.get("event_time", 0)
        meta = event.get("event_meta", {})

        if etype == "PACKET_SENT":
            self._log("ok", f"Sent packet #{pid}     @ {t:.1f}ms")
        elif etype == "PACKET_RECEIVED":
            accepted = meta.get("accepted", True)
            if accepted:
                self._log("ok", f"Recv packet #{pid} → slot #{pid} @ {t:.1f}ms")
            else:
                exp = meta.get("expected", "?")
                self._log("warn", f"DISCARD #{pid} (out-of-order, expected #{exp}) @ {t:.1f}ms")
        elif etype == "PACKET_CORRUPTED":
            self._log("err", f"Packet #{pid} CORRUPTED (target slot #{pid}) @ {t:.1f}ms")
        elif etype == "PACKET_LOST":
            self._log("err", f"Packet #{pid} LOST     (target slot #{pid}) @ {t:.1f}ms")
        elif etype == "ACK_SENT":
            triggered_by_accept = meta.get("from_accept", True)
            if triggered_by_accept:
                self._log("ok", f"ACK #{ack} ← recv (cumulative 0..{ack}) @ {t:.1f}ms")
            else:
                self._log("info", f"ACK #{ack} ← recv (repeat, out-of-order) @ {t:.1f}ms")
        elif etype == "ACK_RECEIVED":
            if meta.get("is_duplicate"):
                self._log("info", f"ACK #{ack} recv (duplicate) @ {t:.1f}ms")
            else:
                self._log("ok", f"ACK #{ack} recv → window slides @ {t:.1f}ms")
        elif etype == "ACK_CORRUPTED":
            self._log("err", f"ACK #{ack} CORRUPTED  @ {t:.1f}ms")
        elif etype == "ACK_LOST":
            self._log("err", f"ACK #{ack} LOST       @ {t:.1f}ms")
        elif etype == "TIMEOUT":
            ws = meta.get("window_start", "?")
            we = meta.get("window_end", "?")
            n_val = meta.get("window_size", "?")
            self._log("warn", f"TIMEOUT #{pid} → RESEND WINDOW [{ws}..{we}] N={n_val} "
                               f"@ {t:.1f}ms")
        elif etype == "DONE":
            self._log("info", "▼ SIMULATION COMPLETE ▼")
        else:
            self._log("info", f"{etype} @ {t:.1f}ms")

    @staticmethod
    def _describe_replay_event(etype: str, pid: int, ack: int, time: float) -> str:
        if etype == "PACKET_SENT":
            return f"Sent packet #{pid}     @ {time:.1f}ms"
        elif etype == "PACKET_RECEIVED":
            return f"Recv packet #{pid} → slot #{pid} @ {time:.1f}ms"
        elif etype == "PACKET_CORRUPTED":
            return f"Packet #{pid} CORRUPTED @ {time:.1f}ms"
        elif etype == "PACKET_LOST":
            return f"Packet #{pid} LOST       @ {time:.1f}ms"
        elif etype == "ACK_SENT":
            return f"ACK #{ack} ← recv @ {time:.1f}ms"
        elif etype == "ACK_RECEIVED":
            return f"ACK #{ack} recv → window slides @ {time:.1f}ms"
        elif etype == "ACK_CORRUPTED":
            return f"ACK #{ack} CORRUPTED  @ {time:.1f}ms"
        elif etype == "ACK_LOST":
            return f"ACK #{ack} LOST       @ {time:.1f}ms"
        elif etype == "TIMEOUT":
            return f"TIMEOUT on #{pid} → retransmit window @ {time:.1f}ms"
        elif etype == "DONE":
            return "▼ SIMULATION COMPLETE ▼"
        return f"{etype} @ {time:.1f}ms"

    def _on_event(self, event) -> None:
        pid = event.packet_id
        ack = event.ack_id

        # Update progress label
        if self._sim:
            self._update_progress(self._sim.delivered, self._sim.num_packets)

        if event.type == EventType.PACKET_SENT:
            self._log("ok", f"Sent packet #{pid}     @ {event.time:.1f}ms")
            self._track_flight(pid, "send", "ok")
        elif event.type == EventType.PACKET_RECEIVED:
            meta = getattr(event, "meta", {}) or {}
            accepted = meta.get("accepted", True)
            if accepted:
                self._log("ok", f"Recv packet #{pid} → slot #{pid} @ {event.time:.1f}ms")
            else:
                exp = meta.get("expected", "?")
                self._log("warn", f"DISCARD #{pid} (out-of-order, expected #{exp}) @ {event.time:.1f}ms")
            self._active_flights.pop(pid, None)
        elif event.type == EventType.PACKET_CORRUPTED:
            self._log("err", f"Packet #{pid} CORRUPTED (target slot #{pid}) @ {event.time:.1f}ms")
            self._show_sender_window_only()
            if pid in self._active_flights:
                self._active_flights[pid]["result"] = "corrupt"
                self._active_flights[pid]["failed_at"] = self._anim_frame
        elif event.type == EventType.PACKET_LOST:
            self._log("err", f"Packet #{pid} LOST     (target slot #{pid}) @ {event.time:.1f}ms")
            self._show_sender_window_only()
            if pid in self._active_flights:
                self._active_flights[pid]["result"] = "lost"
                self._active_flights[pid]["failed_at"] = self._anim_frame
        elif event.type == EventType.ACK_SENT:
            # Cumulative ACK: "I have received packets 0 .. ack."
            # meta.from_accept distinguishes acceptance-triggered vs rejection-triggered.
            meta = getattr(event, "meta", {}) or {}
            triggered_by_accept = meta.get("from_accept", True)
            if triggered_by_accept:
                self._log("ok", f"ACK #{ack} ← recv (cumulative 0..{ack}) @ {event.time:.1f}ms")
            else:
                sn = self._last_snapshot
                exp = sn.get("receiver", {}).get("expected", "?")
                self._log("info", f"ACK #{ack} ← recv (repeat 0..{ack}, still waiting #{exp}) @ {event.time:.1f}ms")
            # Use negative IDs for ACKs to avoid colliding with data packets
            self._track_flight(-ack - 1, "ack", "ok")
        elif event.type == EventType.ACK_RECEIVED:
            meta = getattr(event, "meta", {}) or {}
            sn = self._last_snapshot
            new_base = sn.get("sender", {}).get("base", "?")
            if meta.get("is_duplicate"):
                self._log("info", f"ACK #{ack} recv (dup — base already {new_base} > {ack}) @ {event.time:.1f}ms")
            else:
                self._log("ok", f"ACK #{ack} recv → window slides to base={new_base} @ {event.time:.1f}ms")
                self._show_sender_window_only()
            self._active_flights.pop(-ack - 1, None)
        elif event.type == EventType.ACK_CORRUPTED:
            self._log("err", f"ACK #{ack} CORRUPTED  @ {event.time:.1f}ms")
            self._show_sender_window_only()
            ack_id = -ack - 1
            if ack_id in self._active_flights:
                self._active_flights[ack_id]["result"] = "corrupt"
                self._active_flights[ack_id]["failed_at"] = self._anim_frame
        elif event.type == EventType.ACK_LOST:
            self._log("err", f"ACK #{ack} LOST       @ {event.time:.1f}ms")
            self._show_sender_window_only()
            ack_id = -ack - 1
            if ack_id in self._active_flights:
                self._active_flights[ack_id]["result"] = "lost"
                self._active_flights[ack_id]["failed_at"] = self._anim_frame
        elif event.type == EventType.TIMEOUT:
            meta = getattr(event, "meta", {}) or {}
            ws = meta.get("window_start", "?")
            we = meta.get("window_end", "?")
            n = meta.get("window_size", "?")
            self._log("warn", f"TIMEOUT #{pid} → RESEND WINDOW [{ws}..{we}] N={n} "
                               f"@ {event.time:.1f}ms")
            self._show_sender_window_only()
            self._active_flights.pop(pid, None)

    def _show_sender_window_only(self) -> None:
        """Print minimal sender window state — only on terminal, during errors/timeouts."""
        sn = self._last_snapshot
        if not sn:
            return
        snd = sn.get("sender", {})
        rcv = sn.get("receiver", {})
        base = snd.get("base", "?")
        nxt = snd.get("next_seq", "?")
        win = snd.get("window", [])
        win_size = snd.get("window_size", "?")
        expected = rcv.get("expected", "?")
        sent = snd.get("sent", [])
        rw = snd.get("retransmitting_window")

        if win:
            ws, we = win[0], win[-1]
            marker = ""
            if rw:
                marker = f" ⚡ RESEND [{rw[0]}..{rw[1]}]"
            print(f"[TERM]   ╔══ SENDER [{ws}..{we}] N={win_size}  "
                  f"base={base} next={nxt}{marker}")
        print(f"[TERM]   ╚══ in_flight={sent if sent else '[]'}  "
              f"│ RECEIVER expected={expected}")

    def _track_flight(self, pkt_id: int, direction: str, result: str) -> None:
        """Record a flight start so the canvas can animate it."""
        self._active_flights[pkt_id] = {
            "start_frame": self._anim_frame,
            "direction": direction,
            "result": result,
        }

    def _on_done(self, metrics: dict) -> None:
        self._completed = True
        self._stop_polling()
        self._stop_animation()
        self._replay_capturing = False
        self._update_progress(metrics.get("delivered", 0), metrics.get("delivered", 0))

        # Clear any leftover flying packets/ACKs so the final canvas
        # draw doesn't show a stale "ACK still in the air" dot.
        self._active_flights.clear()

        # Read channel stats BEFORE nulling _sim
        ch_lost = ch_corrupt = 0
        if self._sim:
            ch_lost = self._sim.channel.lost
            ch_corrupt = self._sim.channel.corrupted
            self._sim.stop()
            self._sim = None

        self._set_status(STATUS_COMPLETE)
        self._start_btn.configure(text="Start Simulation", fg_color="#166534",
                                  state="normal")

        # Update metrics
        eff = metrics.get("efficiency", 0) * 100
        tp = metrics.get("throughput_bps", 0) / 1000
        self._cards["throughput"].set(f"{tp:.1f}")
        self._cards["efficiency"].set(f"{eff:.1f}")
        self._cards["retransmissions"].set(str(metrics.get("retransmissions", 0)))
        self._cards["timeouts"].set(str(metrics.get("timeouts", 0)))
        self._cards["delay"].set(f"{metrics.get('avg_delay_ms', 0):.1f}")

        # Channel stats — use actual channel counters, not receiver state
        self._chan_label.configure(
            text=f"Lost: {ch_lost}  Corrupted: {ch_corrupt}")

        # Build a clean completion snapshot so the canvas shows the ideal
        # final state (all packets ACKed, no stale retransmit highlight).
        # Use delivered count (should equal num_packets on completion), NOT
        # total_sent which includes retransmissions.
        n = metrics.get("delivered", 0)
        if n == 0:
            n = self._last_snapshot.get("num_packets", 0)
        self._last_snapshot = {
            "num_packets": n,
            "delivered": n,
            "sender": {
                "base": n,
                "next_seq": n,
                "window_size": self._last_snapshot.get("sender", {}).get("window_size", 4),
                "window": [],
                "sent": [],
                "timed_out": [],
                "retransmitting_window": None,
                "retransmit_frame": 0,
            },
            "receiver": {
                "expected": n,
                "received": list(range(n)),
                "corrupted": [],
            },
        }

        # Record a few clean frames at the end so replay finishes with
        # all packets delivered (not stuck mid-flight / blue).  The DONE
        # event is placed *after* these so _event_to_frame_idx maps it to
        # the last clean frame.
        if self._replay_frames:
            base = self._replay_frames[-1]["anim_frame"]
            for i in range(1, 6):
                self._replay_frames.append({
                    "anim_frame": base + i,
                    "snapshot": dict(self._last_snapshot),
                    "flights": {},
                })
            done_anim = self._replay_frames[-1]["anim_frame"]
        else:
            done_anim = self._anim_frame

        self._replay_events.append({
            "event_type": "DONE",
            "event_time": self._last_snapshot.get("sim_time", 0),
            "event_packet_id": -1,
            "event_ack_id": -1,
            "event_meta": {},
            "anim_frame": done_anim,
        })

        # Force final canvas redraw
        self._redraw_canvas()

        self._log("info", f"COMPLETE — {metrics.get('delivered', 0)}/{n} delivered "
                  f"({metrics.get('total_sent', 0)} sent incl. retransmissions), "
                  f"efficiency={eff:.1f}%, throughput={tp:.1f} kbps")

        # Show replay controls so user can seek through the captured events
        self._log("info", "Replay mode active — drag the seek bar or use ▶/◀ to step through events")
        self._show_replay_controls()

    # ══════════════════════════════════════════════════════════════════════════
    # Event Log
    # ══════════════════════════════════════════════════════════════════════════

    def _log(self, tag: str, text: str) -> None:
        # Terminal echo for debugging
        tag_marker = {"ok": "✓", "err": "✗", "warn": "⚠", "info": "·"}.get(tag, "")
        print(f"[TERM] {tag_marker} {text}")

        self._log_text.configure(state="normal")
        ts = _time.strftime("%H:%M:%S")
        self._log_text.insert("end", f"[{ts}] ", "ts")
        self._log_text.insert("end", text + "\n", tag)
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    # ══════════════════════════════════════════════════════════════════════════
    # Animation Canvas
    # ══════════════════════════════════════════════════════════════════════════

    def _start_animation(self) -> None:
        """Start the canvas animation loop (call during simulation only)."""
        if not self._anim_active:
            self._anim_active = True
            self._schedule_animation()

    def _stop_animation(self) -> None:
        """Stop the animation loop when simulation ends."""
        self._anim_active = False
        if self._anim_id:
            self.after_cancel(self._anim_id)
            self._anim_id = None

    def _schedule_animation(self) -> None:
        """Redraw canvas periodically.
        
        During live simulation: records every frame for later replay.
        During replay mode: plays back pre-recorded frames.
        """
        if not self._anim_active:
            return
        self._anim_frame += 1

        if self._replay_mode:
            # Play back pre-recorded animation frames
            self._playback_animation_frame()
        else:
            # Live simulation — record this frame
            if self._replay_capturing:
                self._replay_frames.append({
                    "anim_frame": self._anim_frame,
                    "snapshot": dict(self._last_snapshot) if self._last_snapshot else {},
                    "flights": {k: dict(v) for k, v in self._active_flights.items()},
                })
            self._redraw_canvas()

        if self._anim_active:
            self._anim_id = self.after(ANIMATION_INTERVAL_MS, self._schedule_animation)

    def _redraw_canvas(self) -> None:
        self._canvas.delete("all")
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()

        snap = self._last_snapshot
        if not snap:
            self._draw_placeholder()
            return

        margin_left = 40
        margin_right = 40

        # Compute layout
        sender_y = 50
        recv_y = h - 130
        mid_y = h / 2

        sender = snap.get("sender", {})
        base = sender.get("base", 0)
        win_size = sender.get("window_size", 4)
        sent = set(sender.get("sent", []))
        timed = set(sender.get("timed_out", []))
        total = snap.get("num_packets", 40)
        rw = sender.get("retransmitting_window")
        rw_frame = sender.get("retransmit_frame", 0)

        recv = snap.get("receiver", {})
        expected = recv.get("expected", 0)
        received = set(recv.get("received", []))
        corrupted = set(recv.get("corrupted", []))

        box = PACKET_BOX_SIZE
        gap = PACKET_SPACING
        slot_w = box + gap  # default slot width

        # ══════════════════════════════════════════════════════════════════════
        # Neon glow background (subtle)
        # ══════════════════════════════════════════════════════════════════════
        if self._neon:
            self._draw_neon_background(w, h)

        # ══════════════════════════════════════════════════════════════════════
        # UNIFIED GRID — compute shared slot width so sender & receiver align
        # ══════════════════════════════════════════════════════════════════════

        win_end = min(base + win_size, total)
        swin_visible = min(win_size, total - base)
        extra_ahead = 3
        s_total_visible = min(swin_visible + extra_ahead, total - base,
                              int((w - margin_left - margin_right) / slot_w))

        max_relevant = min(max(expected + win_size + 2, base + win_size), total - 1)
        r_total = min(max_relevant + 1, total, int((w - margin_left - margin_right) / slot_w))

        # Use one slot width for both rows — scale down if needed
        shared_total = max(s_total_visible, r_total)
        available_w = w - margin_left - margin_right
        if shared_total * slot_w > available_w:
            shared_slot = available_w / max(shared_total, 1)
            shared_box = max(14, shared_slot - 2)
            shared_font = max(7, int(shared_box // 3))
        else:
            shared_slot = slot_w
            shared_box = box
            shared_font = max(9, box // 3)

        # ── Labels ──
        self._canvas.create_text(margin_left, sender_y - 30,
                                  text="SENDER", anchor="w",
                                  fill=COLOR_ACCENT, font=("SF Mono", 15, "bold"))
        self._canvas.create_text(margin_left, recv_y - 30,
                                  text="RECEIVER", anchor="w",
                                  fill=COLOR_SUCCESS, font=("SF Mono", 15, "bold"))

        # ── Channel line ──
        ch_color = "#4f46e5" if self._neon else COLOR_BORDER
        ch_width = 2 if self._neon else 1
        self._canvas.create_line(0, mid_y, w, mid_y, fill=ch_color,
                                  dash=(6, 4), width=ch_width)
        self._canvas.create_text(w // 2, mid_y - 12, text="CHANNEL",
                                  fill=COLOR_TEXT_MUTED, font=("SF Mono", 10))

        # ══════════════════════════════════════════════════════════════════════
        # SENDER WINDOW — aligned by ABSOLUTE packet ID (same grid as receiver)
        # ══════════════════════════════════════════════════════════════════════

        # Store sender slot x-positions for flight targeting
        sender_slot_x: dict[int, float] = {}

        for i in range(s_total_visible):
            pkt = base + i
            if pkt >= total:
                break
            # Position by ABSOLUTE packet ID so sender grid lines up with receiver grid
            x = margin_left + pkt * shared_slot

            if pkt in timed:
                color = COLOR_TIMEOUT
            elif pkt < base:
                color = COLOR_ACKED
            elif pkt in sent:
                color = COLOR_SENT
            else:
                color = COLOR_UNSENT

            self._draw_neon_box(x, sender_y, shared_box, color,
                                text=str(pkt), font=("SF Mono", shared_font, "bold"))
            sender_slot_x[pkt] = x + shared_box / 2

        # ── Window bracket (highlighted during retransmit) ──
        if swin_visible > 0:
            is_resending = rw is not None  # True while retransmit window is active
            # Pulse effect when resending: alternate between red and amber
            if is_resending:
                pulse_phase = (self._anim_frame - rw_frame) % 6
                if pulse_phase < 3:
                    bracket_color = COLOR_ERROR     # red
                else:
                    bracket_color = COLOR_WARNING   # amber
                bracket_w = 3
            else:
                bracket_color = COLOR_ACCENT
                bracket_w = 2

            left_x = margin_left + base * shared_slot
            right_x = margin_left + (base + swin_visible - 1) * shared_slot + shared_box

            # Left bracket
            self._canvas.create_line(left_x - 5, sender_y - 12,
                                      left_x - 5, sender_y + shared_box + 12,
                                      fill=bracket_color, width=bracket_w)
            # Right bracket
            self._canvas.create_line(right_x + 5, sender_y - 12,
                                      right_x + 5, sender_y + shared_box + 12,
                                      fill=bracket_color, width=bracket_w)
            # Top bracket
            self._canvas.create_line(left_x - 5, sender_y - 12,
                                      right_x + 5, sender_y - 12,
                                      fill=bracket_color, width=1)

            label = f"N={win_size}"
            if is_resending:
                label += f"  [RESEND {rw[0]}..{rw[1]}]"
            self._canvas.create_text((left_x + right_x) / 2, sender_y - 20,
                                      text=label, fill=bracket_color,
                                      font=("SF Mono", 9, "bold"))

        # ── Sender trail: faint ghosts of ALL ACKed packets (0 .. base-1) ──
        for pkt in range(base):
            x = margin_left + pkt * shared_slot
            # Only draw what's on-screen; skip packets scrolled far left
            if x + shared_box < margin_left:
                continue
            self._canvas.create_rectangle(
                x, sender_y, x + shared_box, sender_y + shared_box,
                fill=COLOR_ACKED, outline=COLOR_BORDER, width=1, stipple="gray50",
            )
            self._canvas.create_text(
                x + shared_box / 2, sender_y + shared_box / 2,
                text=str(pkt), fill=COLOR_TEXT_MUTED,
                font=("SF Mono", shared_font, "bold"),
            )

        # ══════════════════════════════════════════════════════════════════════
        # RECEIVER BUFFER — aligned by ABSOLUTE packet ID (same grid as sender)
        # ══════════════════════════════════════════════════════════════════════

        # Store receiver slot x-positions for flight landing
        recv_slot_x: dict[int, float] = {}

        for i in range(r_total):
            pkt = i  # absolute packet ID
            x = margin_left + pkt * shared_slot

            if pkt in received:
                # Match sender trail: gray stipple + ACKED fill for sync
                self._canvas.create_rectangle(
                    x, recv_y, x + shared_box, recv_y + shared_box,
                    fill=COLOR_ACKED, outline=COLOR_BORDER, width=1,
                    stipple="gray50",
                )
                self._canvas.create_text(
                    x + shared_box / 2, recv_y + shared_box / 2,
                    text=str(pkt), fill=COLOR_TEXT_MUTED,
                    font=("SF Mono", shared_font, "bold"),
                )
                recv_slot_x[pkt] = x + shared_box / 2
                continue
            elif pkt in corrupted:
                color = COLOR_TIMEOUT
            elif pkt == expected:
                color = COLOR_BG_HIGHLIGHT
            else:
                color = COLOR_UNSENT

            self._draw_neon_box(x, recv_y, shared_box, color,
                                text=str(pkt), font=("SF Mono", shared_font, "bold"))
            recv_slot_x[pkt] = x + shared_box / 2

        # Expected marker
        if expected < r_total:
            ex_x = recv_slot_x.get(expected, margin_left + expected * shared_slot + shared_box / 2)
            self._canvas.create_text(ex_x, recv_y - 14,
                                      text=f"Expected #{expected}", fill=COLOR_ACCENT,
                                      font=("SF Mono", 9, "bold"))

        # ══════════════════════════════════════════════════════════════════════
        # FLYING PACKETS — X-interpolation from sender → receiver
        # ══════════════════════════════════════════════════════════════════════

        if self._active_flights:
            dot_r = 7
            flight_frames = max(self._FLIGHT_FRAMES, 1)
            fail_disp = self._FAIL_DISPLAY_FRAMES
            fail_point = self._FAIL_POINT

            # Track occupied positions to prevent overlap
            occupied: dict[tuple[int, int], int] = {}  # (grid_x, grid_y) → count

            for flight_id, flight in list(self._active_flights.items()):
                elapsed = self._anim_frame - flight["start_frame"]
                direction = flight["direction"]
                result = flight.get("result", "ok")
                is_failure = result in ("lost", "corrupt")

                # ── Progress & cleanup ──
                if is_failure:
                    progress = min(elapsed / flight_frames, fail_point)
                    failed_at = flight.get("failed_at", self._anim_frame)
                    fail_elapsed = self._anim_frame - failed_at
                    if fail_elapsed > fail_disp:
                        del self._active_flights[flight_id]
                        continue
                else:
                    progress = min(elapsed / flight_frames, 1.0)
                    if progress >= 1.0:
                        if elapsed > flight_frames + 2:
                            del self._active_flights[flight_id]
                            continue

                # ── Determine display packet ID ──
                if flight_id < 0:
                    display_pkt = -flight_id - 1
                else:
                    display_pkt = flight_id

                # ── X interpolation: sender slot → receiver slot ──
                # Start X: position on sender (relative to window base)
                sender_col = display_pkt - base
                if sender_col >= 0 and display_pkt in sender_slot_x:
                    start_x = sender_slot_x[display_pkt]
                elif sender_col < 0:
                    # Off-screen left — pin to left edge
                    start_x = margin_left + dot_r + 4
                else:
                    # Off-screen right — pin to right edge
                    start_x = w - margin_right - dot_r

                # End X: absolute position on receiver
                if display_pkt in recv_slot_x:
                    end_x = recv_slot_x[display_pkt]
                else:
                    # Fallback: compute from slot width
                    end_x = margin_left + display_pkt * shared_slot + shared_box / 2

                # Interpolate X based on progress
                t = progress
                ease = t * t * (3 - 2 * t)
                x = start_x + ease * (end_x - start_x)

                # Clamp X to canvas bounds
                x = max(margin_left + dot_r, min(x, w - margin_right - dot_r))

                # ── Y position ──
                top_y = sender_y + shared_box + dot_r
                bot_y = recv_y - dot_r

                if direction in ("send", "resend"):
                    y = top_y + ease * (bot_y - top_y)
                else:
                    y = bot_y - ease * (bot_y - top_y)

                # ── Stagger: prevent overlap at same position ──
                grid_key = (int(x / (dot_r * 2)), int(y / (dot_r * 2)))
                same_spot = occupied.get(grid_key, 0)
                if same_spot > 0:
                    stagger_dx = (same_spot % 3 - 1) * dot_r * 2
                    stagger_dy = ((same_spot // 3) % 3 - 1) * dot_r * 2
                    x += stagger_dx
                    y += stagger_dy
                occupied[grid_key] = same_spot + 1

                # ── Color ──
                if direction == "ack":
                    fill = COLOR_ERROR if is_failure else COLOR_ACCENT
                elif is_failure:
                    fill = COLOR_ERROR
                else:
                    color_map = {
                        "ok": COLOR_SUCCESS,
                        "timeout": COLOR_WARNING,
                        "dup": COLOR_TEXT_MUTED,
                    }
                    fill = color_map.get(result, COLOR_ACCENT)

                # ── Draw dot ──
                self._canvas.create_oval(
                    x - dot_r, y - dot_r, x + dot_r, y + dot_r,
                    fill=fill, outline=COLOR_ERROR if is_failure else "",
                    width=1.5 if is_failure else 0, tags="flight"
                )

                # ── Label ──
                if is_failure:
                    self._canvas.create_text(
                        x, y, text="✗",
                        fill=COLOR_ERROR, font=("SF Mono", 12, "bold"),
                        tags="flight"
                    )
                else:
                    label = f"#{display_pkt}" if flight_id >= 0 else f"ACK{display_pkt}"
                    self._canvas.create_text(
                        x, y + dot_r + 8, text=label,
                        fill=fill, font=("SF Mono", 7), tags="flight"
                    )

                # ── Direction arrow ──
                if is_failure and progress >= fail_point:
                    pass
                elif direction in ("send", "resend"):
                    arrow_tip_y = y + dot_r
                    self._canvas.create_line(
                        x, y - dot_r, x, arrow_tip_y,
                        fill=fill, width=1.5, tags="flight"
                    )
                    self._canvas.create_polygon(
                        x - 3, arrow_tip_y - 4, x + 3, arrow_tip_y - 4, x, arrow_tip_y,
                        fill=fill, outline="", tags="flight"
                    )
                else:
                    arrow_tip_y = y - dot_r
                    self._canvas.create_line(
                        x, y + dot_r, x, arrow_tip_y,
                        fill=fill, width=1.5, tags="flight"
                    )
                    self._canvas.create_polygon(
                        x - 3, arrow_tip_y + 4, x + 3, arrow_tip_y + 4, x, arrow_tip_y,
                        fill=fill, outline="", tags="flight"
                    )

        # ══════════════════════════════════════════════════════════════════════
        # STEP-MODE PAUSED BANNER
        # ══════════════════════════════════════════════════════════════════════
        if self._step_paused:
            banner_y = mid_y
            self._canvas.create_rectangle(
                w / 2 - 140, banner_y - 18, w / 2 + 140, banner_y + 18,
                fill=COLOR_BG_PANEL, outline=COLOR_WARNING, width=2, stipple="gray75",
            )
            self._canvas.create_text(
                w / 2, banner_y,
                text="⏸  STEP PAUSED — click Next Step to continue",
                fill=COLOR_WARNING, font=("SF Mono", 11, "bold"),
            )

        # ══════════════════════════════════════════════════════════════════════
        # FOOTER: info + legend
        # ══════════════════════════════════════════════════════════════════════

        delivered = snap.get("delivered", 0)
        sent_count = len(sent)
        footer_y = recv_y + shared_box + 18
        self._canvas.create_text(margin_left, footer_y,
                                  text=f"Delivered: {delivered}/{total}  |  "
                                       f"Sent (unACKed): {sent_count}",
                                  anchor="w", fill=COLOR_TEXT_MUTED,
                                  font=("SF Mono", 11))

        lx = w - margin_right - 120
        items = [
            (COLOR_SENT, "Sent / UnACKed"),
            (COLOR_ACKED, "ACKed / Received"),
            (COLOR_TIMEOUT, "Timed out / Corrupt"),
            (COLOR_UNSENT, "Not yet sent"),
        ]
        for i, (c, lbl) in enumerate(items):
            y = footer_y + i * 18
            self._canvas.create_rectangle(lx, y, lx + 12, y + 12, fill=c, outline="")
            self._canvas.create_text(lx + 18, y + 6, text=lbl, anchor="w",
                                      fill=COLOR_TEXT_MUTED, font=("SF Mono", 10))

    def _draw_neon_background(self, w: int, h: int) -> None:
        """Subtle radial glow effect for neon mode."""
        for i in range(3):
            r = 50 + i * 30
            alpha = 3 - i  # fading opacity via stipple
            cx, cy = w // 2, h // 2
            self._canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                      fill="", outline="#6366f1",
                                      width=1, dash=(1, alpha * 4))

    def _draw_neon_box(self, x: float, y: float, size: float, fill: str,
                        outline: str = "", text: str = "", text_color: str = "",
                        font=("SF Mono", 9, "bold"), pulse: bool = False) -> None:
        """Draw a packet box with optional neon bright border."""
        if self._neon:
            # Bright border only — no noisy bubble halos
            self._canvas.create_rectangle(
                x, y, x + size, y + size,
                fill=fill, outline="#a5b4fc", width=2,
            )
        else:
            self._canvas.create_rectangle(
                x, y, x + size, y + size,
                fill=fill, outline=outline or COLOR_BORDER, width=1,
            )
        if text:
            self._canvas.create_text(
                x + size / 2, y + size / 2,
                text=text, fill=text_color or COLOR_TEXT,
                font=font,
            )

    def _draw_placeholder(self) -> None:
        try:
            w = self._canvas.winfo_width()
            h = self._canvas.winfo_height()
        except Exception:
            return  # canvas not ready yet
        if w < 100 or h < 100:
            self.after(200, self._draw_placeholder)  # retry later
            return
        self._canvas.delete("all")
        self._canvas.create_text(w // 2, h // 2,
                                  text="Click 'Start Simulation'\nto begin",
                                  fill=COLOR_TEXT_MUTED, font=("SF Mono", 14),
                                  justify="center")

    # ══════════════════════════════════════════════════════════════════════════
    # Cleanup
    # ══════════════════════════════════════════════════════════════════════════

    def _on_close(self) -> None:
        self._stop_polling()
        self._stop_animation()
        if self._sim:
            self._sim.stop()
            self._sim = None
        try:
            self.destroy()
        except Exception:
            pass

    def _force_quit(self) -> None:
        """Hard exit — use when the window is frozen."""
        import os
        try:
            self._stop_polling()
            self._stop_animation()
            if self._sim:
                self._sim.stop()
                self._sim = None
            self.destroy()
        except Exception:
            pass
        os._exit(0)
