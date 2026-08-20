"""Widget construction for the GBN Lab application."""

import customtkinter as ctk
import tkinter as tk

from config import (
    DEFAULT_WINDOW_SIZE,
    DEFAULT_BER,
    DEFAULT_PACKET_LOSS,
    DEFAULT_NUM_PACKETS,
    DEFAULT_SIM_SPEED,
    SCENARIO_PRESETS,
    CANVAS_WEIGHT,
    EVENT_LOG_WEIGHT,
    EVENT_LOG_HEIGHT,
    MONO_FONT,
    COLOR_BG,
    COLOR_BG_PANEL,
    COLOR_BG_HIGHLIGHT,
    COLOR_ACCENT,
    COLOR_SUCCESS,
    COLOR_ERROR,
    COLOR_WARNING,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    COLOR_BORDER,
    STATUS_IDLE,
    STATUS_RUNNING,
    STATUS_COMPLETE,
)


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


class UIBuilderMixin:
    """Builds every widget in the GBN Lab window."""

    _STATUS_COLORS = {
        STATUS_IDLE: "#475569",
        STATUS_RUNNING: COLOR_SUCCESS,
        STATUS_COMPLETE: COLOR_ACCENT,
    }

    def _build_ui(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=COLOR_BG, height=44, corner_radius=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        ctk.CTkLabel(bar, text="GBN Lab",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=COLOR_ACCENT).pack(side="left", padx=16, pady=10)
        ctk.CTkLabel(bar, text="by E_force Software",
                     font=ctk.CTkFont(size=10),
                     text_color=COLOR_TEXT_MUTED).pack(side="left", padx=(4, 0), pady=10)

        self._status_dot = tk.Canvas(bar, width=14, height=14,
                                     bg=COLOR_BG, highlightthickness=0)
        self._status_dot.pack(side="right", padx=(0, 6), pady=10)
        self._dot = self._status_dot.create_oval(
            2, 2, 12, 12, fill="#475569", outline="")

        self._status_label = ctk.CTkLabel(bar, text="Idle", font=ctk.CTkFont(size=13),
                                          text_color=COLOR_TEXT_MUTED)
        self._status_label.pack(side="right", padx=(0, 20), pady=10)

        ctk.CTkFrame(self, fg_color=COLOR_BORDER, height=1).pack(fill="x")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)

        body.grid_columnconfigure(0, weight=0, minsize=200)
        body.grid_columnconfigure(1, weight=3)
        body.grid_columnconfigure(2, weight=0, minsize=230)
        body.grid_rowconfigure(0, weight=1)

        self._body_frame = body

        self._build_controls(body)
        self._build_center(body)
        self._build_metrics_panel(body)

    def _build_controls(self, parent) -> None:
        panel = ctk.CTkFrame(parent, fg_color=COLOR_BG_PANEL, corner_radius=0)
        panel.grid(row=0, column=0, sticky="ns")

        ctk.CTkLabel(panel, text="Parameters", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=COLOR_ACCENT).pack(padx=14, pady=(14, 4), anchor="w")

        ctk.CTkLabel(panel, text="Scenario", font=ctk.CTkFont(size=11),
                     text_color=COLOR_TEXT_MUTED).pack(padx=14, pady=(6, 0), anchor="w")
        self._scenario_var = ctk.StringVar(value="Custom")
        scenario_names = ["Custom"] + list(SCENARIO_PRESETS.keys())
        self._scenario_menu = ctk.CTkOptionMenu(
            panel, values=scenario_names, variable=self._scenario_var,
            command=self._on_scenario_select,
            fg_color=COLOR_BG_HIGHLIGHT, button_color=COLOR_ACCENT,
            text_color=COLOR_TEXT, dropdown_fg_color=COLOR_BG_PANEL,
            font=ctk.CTkFont(size=11), width=170,
        )
        self._scenario_menu.pack(padx=14, pady=(2, 8))

        self._window_slider, self._window_val = self._slider(
            panel, "Window Size (N)", DEFAULT_WINDOW_SIZE, 1, 10, 1)
        self._ber_slider, self._ber_val = self._slider(
            panel, "Bit Error Rate", DEFAULT_BER, 0.0, 0.01, 0.0001)
        self._loss_slider, self._loss_val = self._slider(
            panel, "Packet Loss", DEFAULT_PACKET_LOSS, 0.0, 0.5, 0.01)
        self._packets_slider, self._packets_val = self._slider(
            panel, "Packets to Send", DEFAULT_NUM_PACKETS, 1, 15, 1)
        self._speed_slider, self._speed_val = self._slider(
            panel, "Simulation Speed", DEFAULT_SIM_SPEED, 0.1, 2.0, 0.1)
        self._speed_slider.configure(
            command=lambda v: self._speed_val.configure(text=f"{float(v):.1f}x"))

        guide = (
            "Pick a scenario above, then\n"
            "click Run. Step-by-Step mode\n"
            "pauses on anomalies like timeouts\n"
            "and packet loss."
        )
        ctk.CTkLabel(panel, text=guide, font=ctk.CTkFont(size=10),
                     text_color=COLOR_TEXT_MUTED, justify="left",
                     wraplength=170).pack(padx=14, pady=(20, 10), anchor="w")

        self._step_mode_var = ctk.BooleanVar(value=False)
        self._step_switch = ctk.CTkSwitch(
            panel, text="Step-by-Step Mode", variable=self._step_mode_var,
            command=self._on_step_mode_toggle,
            font=ctk.CTkFont(size=11),
            progress_color=COLOR_ACCENT, button_color=COLOR_TEXT,
            text_color=COLOR_TEXT_MUTED,
        )
        self._step_switch.pack(padx=14, pady=(0, 2), anchor="w")

        ctk.CTkLabel(panel, text="Pauses on anomalies like timeouts, loss, corruption",
                     font=ctk.CTkFont(size=9),
                     text_color=COLOR_TEXT_MUTED, justify="left",
                     ).pack(padx=28, pady=(0, 6), anchor="w")

        btn_opts = {"width": 170, "height": 36,
                    "font": ctk.CTkFont(size=13, weight="bold")}

        self._start_btn = ctk.CTkButton(
            panel, text="Start Simulation", fg_color="#166534",
            hover_color="#14532d", command=self._on_start, **btn_opts)
        self._start_btn.pack(padx=14, pady=(10, 6))

        self._stop_btn = ctk.CTkButton(
            panel, text="Reset", fg_color="#475569", hover_color="#334155",
            command=self._on_reset, **btn_opts)
        self._stop_btn.pack(padx=14, pady=(0, 4))

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

    def _build_center(self, parent) -> None:
        center = ctk.CTkFrame(parent, fg_color="transparent")
        center.grid(row=0, column=1, sticky="nsew", padx=(6, 6))
        center.grid_rowconfigure(0, weight=CANVAS_WEIGHT)
        center.grid_rowconfigure(1, weight=0, minsize=36)
        center.grid_rowconfigure(2, weight=EVENT_LOG_WEIGHT)
        center.grid_columnconfigure(0, weight=1)
        center.grid_columnconfigure(1, weight=0)

        self._center_frame = center

        self._canvas = tk.Canvas(center, bg=COLOR_BG, highlightthickness=0)
        self._canvas.grid(row=0, column=0, sticky="nsew", pady=(0, 2))

        scrub_frame = ctk.CTkFrame(center, fg_color=COLOR_BG_PANEL, corner_radius=6,
                                   height=36)
        scrub_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 2))
        scrub_frame.pack_propagate(False)
        scrub_frame.grid_propagate(False)

        self._sim_progress_frame = ctk.CTkFrame(scrub_frame, fg_color="transparent",
                                                height=34)
        self._sim_progress_frame.pack(fill="x", expand=True)

        self._progress_label = ctk.CTkLabel(
            self._sim_progress_frame, text="Progress: --/--",
            font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED,
        )
        self._progress_label.pack(side="left", padx=(12, 0))

        self._replay_frame = ctk.CTkFrame(scrub_frame, fg_color="transparent",
                                          height=34)

        self._replay_slider_var = ctk.IntVar(value=0)
        self._replay_slider = ctk.CTkSlider(
            self._replay_frame, from_=0, to=1, variable=self._replay_slider_var,
            command=self._on_replay_seek,
            progress_color=COLOR_ACCENT, button_color=COLOR_ACCENT, height=14,
        )
        self._replay_slider.pack(
            side="left", fill="x", expand=True, padx=(8, 6))

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
        self._replay_pos_label.pack(
            side="right", padx=(0, 8), fill="x", expand=True)

        log_frame = ctk.CTkFrame(
            center, fg_color=COLOR_BG_PANEL, corner_radius=8)
        log_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=4, pady=(4, 4))
        log_frame.grid_rowconfigure(1, weight=1)
        log_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(log_frame, text="Event Log",
                     font=ctk.CTkFont(size=11),
                     text_color=COLOR_TEXT_MUTED).grid(
            row=0, column=0, sticky="w", padx=8, pady=(3, 1))

        self._log_text = tk.Text(log_frame, bg="#0f172a", fg=COLOR_TEXT,
                                 font=(MONO_FONT, 16), wrap="word",
                                 bd=0, padx=8, pady=4, height=EVENT_LOG_HEIGHT,
                                 insertbackground=COLOR_ACCENT,
                                 highlightthickness=0, state="disabled")
        self._log_text.grid(row=1, column=0, columnspan=2, sticky="nsew",
                            padx=4, pady=(2, 4))

        self._log_text.tag_configure("ok", foreground=COLOR_SUCCESS)
        self._log_text.tag_configure("err", foreground=COLOR_ERROR)
        self._log_text.tag_configure("warn", foreground=COLOR_WARNING)
        self._log_text.tag_configure("info", foreground=COLOR_ACCENT)
        self._log_text.tag_configure("ts", foreground=COLOR_TEXT_MUTED,
                                     font=(MONO_FONT, 13))

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

        ctk.CTkLabel(panel, text="Channel Stats", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=COLOR_TEXT_MUTED).pack(padx=14, pady=(14, 4), anchor="w")
        self._chan_label = ctk.CTkLabel(panel, text="Lost: --  Corrupted: --",
                                        font=ctk.CTkFont(size=12),
                                        text_color=COLOR_TEXT_MUTED)
        self._chan_label.pack(padx=14, anchor="w")

    def _set_status(self, status: str) -> None:
        color = self._STATUS_COLORS.get(status, "#475569")
        self._status_dot.itemconfig(self._dot, fill=color)
        self._status_label.configure(text=status, text_color=color)
