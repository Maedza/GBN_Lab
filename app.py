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

        # Flying packet animation state
        self._active_flights: dict[int, dict] = {}   # pkt_id -> {start_frame, direction, result, failed_at?}
        self._FLIGHT_FRAMES = 6                       # animation frames per flight hop
        self._FAIL_POINT = 0.65                       # where failed packets stop mid-flight
        self._FAIL_DISPLAY_FRAMES = 10                # frames to show X before removing

        self._build_ui()

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

        self._window_slider, self._window_val = self._slider(
            panel, "Window Size (N)", DEFAULT_WINDOW_SIZE, 1, 10, 1)
        self._ber_slider, self._ber_val = self._slider(
            panel, "Bit Error Rate", DEFAULT_BER, 0.0, 0.01, 0.0001)
        self._loss_slider, self._loss_val = self._slider(
            panel, "Packet Loss", DEFAULT_PACKET_LOSS, 0.0, 0.5, 0.01)
        self._timeout_slider, self._timeout_val = self._slider(
            panel, "Timeout (ms)", DEFAULT_TIMEOUT_MS, 100, 2000, 50)
        self._packets_slider, self._packets_val = self._slider(
            panel, "Packets to Send", DEFAULT_NUM_PACKETS, 5, 200, 5)
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
        center.grid_rowconfigure(1, weight=1)
        center.grid_columnconfigure(0, weight=1)

        # Canvas
        self._canvas = tk.Canvas(center, bg=COLOR_BG, highlightthickness=0)
        self._canvas.grid(row=0, column=0, sticky="nsew", pady=(0, 4))

        # Event log
        log_frame = ctk.CTkFrame(center, fg_color=COLOR_BG_PANEL, corner_radius=8)
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(log_frame, fg_color="transparent", height=26)
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 0))
        ctk.CTkLabel(header, text="Event Log", font=ctk.CTkFont(size=11, weight="bold"),
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

        # Log initial info BEFORE starting the sim so it appears first
        self._log("info", f"Go-Back-N |  N={window_size}  BER={ber:.4f}  "
                  f"loss={packet_loss:.0%}  pkts={num_packets}  timeout={timeout_ms}ms")

        self._sim.start()
        self._set_status(STATUS_RUNNING)
        self._start_btn.configure(text="Running...", fg_color="#475569", state="disabled")
        self._completed = False

        # Start polling
        self._start_polling()

        # Start animation (only during simulation)
        self._start_animation()

    def _on_reset(self) -> None:
        if self._sim:
            self._sim.stop()
            self._sim = None
        self._stop_polling()
        self._stop_animation()
        self._reset_ui()
        self._set_status(STATUS_IDLE)
        self._start_btn.configure(text="Start Simulation", fg_color="#166534",
                                  state="normal")

    def _reset_ui(self) -> None:
        for card in self._cards.values():
            card.set("--")
        self._chan_label.configure(text="Lost: --  Corrupted: --")
        # Keep log history across runs — add a separator if there was content
        log_already_has_content = self._log_text.get("1.0", "end-1c").strip() != ""
        self._log_text.configure(state="normal")
        if log_already_has_content:
            self._log_text.insert("end", "\n" + "─" * 50 + " NEW RUN " + "─" * 50 + "\n\n", "info")
        self._log_text.configure(state="disabled")
        self._events.clear()
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

        for msg in self._sim.poll():
            t = msg["type"]
            if t == "event":
                # Update snapshot BEFORE _on_event so _dump_window sees current state
                self._last_snapshot = msg.get("state_snapshot", {})
                self._on_event(msg["event"])
            elif t == "tick":
                self._last_snapshot = msg.get("state_snapshot", {})
            elif t == "done":
                self._on_done(msg.get("metrics", {}))
                return  # _on_done sets _sim = None, stop polling

        # Guard: _on_done may have cleared _sim
        if self._sim is None:
            return

        if self._sim.running:
            self._poll_id = self.after(GUI_UPDATE_INTERVAL_MS, self._poll)
        elif not self._completed:
            if self._sim.delivered >= self._sim.num_packets:
                self._on_done(self._sim.metrics)

    def _on_event(self, event) -> None:
        pid = event.packet_id
        ack = event.ack_id

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
        n = metrics.get("total_sent", 0)  # use total_sent as proxy for num_packets
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

        # Force final canvas redraw
        self._redraw_canvas()

        self._log("info", f"COMPLETE — {metrics.get('delivered', 0)}/{metrics.get('total_sent', 0)} "
                  f"delivered, efficiency={eff:.1f}%, throughput={tp:.1f} kbps")

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
        """Redraw canvas periodically — only when anim_active is True."""
        if not self._anim_active:
            return
        self._anim_frame += 1
        self._redraw_canvas()
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
        self._canvas.create_text(margin_left, sender_y - 24,
                                  text="SENDER", anchor="w",
                                  fill=COLOR_ACCENT, font=("SF Mono", 14, "bold"))
        self._canvas.create_text(margin_left, recv_y - 24,
                                  text="RECEIVER", anchor="w",
                                  fill=COLOR_SUCCESS, font=("SF Mono", 14, "bold"))

        # ── Channel line ──
        self._canvas.create_line(0, mid_y, w, mid_y, fill=COLOR_BORDER,
                                  dash=(6, 4), width=1)
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

            self._canvas.create_rectangle(x, sender_y, x + shared_box, sender_y + shared_box,
                                           fill=color, outline=COLOR_BORDER, width=1,
                                           tags="pkt")
            self._canvas.create_text(x + shared_box / 2, sender_y + shared_box / 2,
                                      text=str(pkt), fill=COLOR_TEXT,
                                      font=("SF Mono", shared_font, "bold"),
                                      tags="pkt")
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

        # ══════════════════════════════════════════════════════════════════════
        # RECEIVER BUFFER — aligned by ABSOLUTE packet ID (same grid as sender)
        # ══════════════════════════════════════════════════════════════════════

        # Store receiver slot x-positions for flight landing
        recv_slot_x: dict[int, float] = {}

        for i in range(r_total):
            pkt = i  # absolute packet ID
            x = margin_left + pkt * shared_slot

            if pkt in received:
                color = COLOR_ACKED
            elif pkt in corrupted:
                color = COLOR_TIMEOUT
            elif pkt == expected:
                color = COLOR_BG_HIGHLIGHT
            else:
                color = COLOR_UNSENT

            self._canvas.create_rectangle(x, recv_y, x + shared_box, recv_y + shared_box,
                                           fill=color, outline=COLOR_BORDER, width=1,
                                           tags="pkt")
            self._canvas.create_text(x + shared_box / 2, recv_y + shared_box / 2,
                                      text=str(pkt), fill=COLOR_TEXT,
                                      font=("SF Mono", shared_font, "bold"),
                                      tags="pkt")
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
        # FOOTER: info + legend
        # ══════════════════════════════════════════════════════════════════════

        delivered = snap.get("delivered", 0)
        sent_count = len(sent)
        self._canvas.create_text(margin_left, recv_y + shared_box + 16,
                                  text=f"Delivered: {delivered}/{total}  |  "
                                       f"Sent (unacked): {sent_count}",
                                  anchor="w", fill=COLOR_TEXT_MUTED,
                                  font=("SF Mono", 11))

        lx = w - margin_right - 120
        ly = recv_y + shared_box + 40
        items = [
            (COLOR_SENT, "Sent / UnACKed"),
            (COLOR_ACKED, "ACKed / Received"),
            (COLOR_TIMEOUT, "Timed out / Corrupt"),
            (COLOR_UNSENT, "Not yet sent"),
        ]
        for i, (c, lbl) in enumerate(items):
            y = ly + i * 16
            self._canvas.create_rectangle(lx, y, lx + 10, y + 10, fill=c, outline="")
            self._canvas.create_text(lx + 16, y + 5, text=lbl, anchor="w",
                                      fill=COLOR_TEXT_MUTED, font=("SF Mono", 8))

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
