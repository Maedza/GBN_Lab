"""Simulation lifecycle: scenario presets, start/reset, polling, step mode."""

import customtkinter as ctk

from config import (
    SCENARIO_PRESETS,
    DEFAULT_PACKET_SIZE_BITS,
    DEFAULT_DATA_RATE_KBPS,
    DEFAULT_PROPAGATION_DELAY_MS,
    GUI_UPDATE_INTERVAL_MS,
    COLOR_BG_PANEL,
    COLOR_WARNING,
    COLOR_ACCENT,
    COLOR_TEXT_MUTED,
    COLOR_SUCCESS,
    STATUS_IDLE,
    STATUS_RUNNING,
)
from simulation import GBNSimulation, EventType


class SimControlMixin:
    """Scenario selection, run lifecycle, polling, and step-mode pausing."""

    def _on_scenario_select(self, name: str) -> None:
        """Load a preset scenario's parameters into the sliders.

        sim_speed is intentionally NOT set — it is a visual preference the
        user controls. Changing a scenario should not change playback speed.
        """
        if name == "Custom":
            return
        preset = SCENARIO_PRESETS.get(name)
        if not preset:
            return
        self._window_slider.set(preset["window_size"])
        self._ber_slider.set(preset["ber"])
        self._loss_slider.set(preset["packet_loss"])
        self._packets_slider.set(preset["num_packets"])
        self._window_val.configure(text=str(preset["window_size"]))
        self._ber_val.configure(text=f"{preset['ber']:.4f}")
        self._loss_val.configure(text=f"{preset['packet_loss']:.2f}")
        self._packets_val.configure(text=str(preset["num_packets"]))

    def _on_step_mode_toggle(self) -> None:
        self._step_mode = self._step_mode_var.get()

    def _on_start(self) -> None:
        self._reset_ui()

        window_size = int(self._window_slider.get())
        ber = round(self._ber_slider.get(), 4)
        packet_loss = round(self._loss_slider.get(), 4)
        timeout_ms = 0
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

        self._sim_speed_replay = sim_speed

        self._log("info", f"Go-Back-N |  N={window_size}  BER={ber:.4f}  "
                  f"loss={packet_loss:.0%}  pkts={num_packets}  timeout=auto")

        self._sim.start()
        self._set_status(STATUS_RUNNING)

        if self._step_mode:
            self._start_btn.configure(
                text="Running (Step)...", fg_color="#475569", state="disabled")
            self._step_paused = False
        else:
            self._start_btn.configure(
                text="Running...", fg_color="#475569", state="disabled")

        self._completed = False

        self._replay_capturing = True
        self._replay_frames.clear()
        self._replay_events.clear()

        self._start_polling()
        self._start_animation()

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
        self._stop_replay_auto()
        self._replay_mode = False
        self._replay_frame.pack_forget()
        self._sim_progress_frame.pack(fill="x", expand=True)
        log_already_has_content = self._log_text.get(
            "1.0", "end-1c").strip() != ""
        self._log_text.configure(state="normal")
        if log_already_has_content:
            self._log_text.insert("end", "\n" + "─" *
                                  50 + " NEW RUN " + "─" * 50 + "\n\n", "info")
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
        self._pending_snapshot = None
        self._slide_delay = 0
        self._active_flights.clear()
        self._canvas.delete("all")
        self._draw_placeholder()

    def _start_polling(self) -> None:
        if self._poll_id:
            self.after_cancel(self._poll_id)
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
            self._poll_id = self.after(GUI_UPDATE_INTERVAL_MS, self._poll)
            return

        for msg in self._sim.poll():
            t = msg["type"]
            if t == "event":
                old_snap = dict(self._last_snapshot) if self._last_snapshot else {}
                self._last_snapshot = msg.get("state_snapshot", {})
                self._on_event(msg["event"])
                if self._slide_delay > 0:
                    self._pending_snapshot = dict(self._last_snapshot)
                    self._last_snapshot = old_snap
                evt = msg["event"]
                self._replay_events.append({
                    "event_type": evt.type,
                    "event_time": evt.time,
                    "event_packet_id": evt.packet_id,
                    "event_ack_id": evt.ack_id,
                    "event_meta": dict(getattr(evt, "meta", {}) or {}),
                    "anim_frame": self._anim_frame,
                })

                if self._step_mode:
                    if evt.type not in self._SKIP_EVENTS:
                        if evt.type == self._last_paused_anomaly:
                            pass
                        else:
                            self._last_paused_anomaly = evt.type
                            self._step_paused = True
                            self._pause_for_step(evt)
                            return

            elif t == "tick":
                self._last_snapshot = msg.get("state_snapshot", {})
            elif t == "done":
                self._destroy_step_frame()
                self._on_done(msg.get("metrics", {}))
                return

        if self._sim is None:
            return

        if self._sim.running:
            self._poll_id = self.after(GUI_UPDATE_INTERVAL_MS, self._poll)
        elif not self._completed:
            if self._sim.delivered >= self._sim.num_packets:
                self._destroy_step_frame()
                self._on_done(self._sim.metrics)

    _SKIP_EVENTS = {EventType.PACKET_SENT, EventType.PACKET_RECEIVED,
                    EventType.ACK_SENT, EventType.ACK_RECEIVED}

    def _destroy_step_frame(self) -> None:
        if hasattr(self, "_step_frame") and self._step_frame.winfo_exists():
            self._step_frame.destroy()

    _STEP_AUTO_SECONDS = 4

    def _pause_for_step(self, event) -> None:
        self._step_paused = True
        self._destroy_step_frame()

        self._step_frame = ctk.CTkFrame(self, fg_color=COLOR_BG_PANEL, corner_radius=8,
                                        border_width=1, border_color=COLOR_WARNING)
        self._step_frame.pack(side="bottom", fill="x", padx=20, pady=10)

        row = ctk.CTkFrame(self._step_frame, fg_color="transparent")
        row.pack(padx=12, pady=(8, 8))

        ctk.CTkLabel(
            row, text=f"⏸  {event.type}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_WARNING,
        ).pack(side="left", padx=(0, 12))

        self._step_countdown = self._STEP_AUTO_SECONDS
        self._step_timer_label = ctk.CTkLabel(
            row, text=f"Auto-continue in {self._step_countdown}s…",
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_MUTED,
        )
        self._step_timer_label.pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            row, text="Next →", fg_color=COLOR_ACCENT,
            hover_color="#0284c7", command=self._on_step_continue,
            font=ctk.CTkFont(size=11, weight="bold"), width=70, height=28,
        ).pack(side="left")

        self._tick_step_countdown()

    def _tick_step_countdown(self) -> None:
        """Decrement countdown; auto-continue when it reaches 0."""
        if not self._step_paused or not hasattr(self, "_step_frame"):
            return
        if not self._step_frame.winfo_exists():
            return

        self._step_countdown -= 1
        if self._step_countdown <= 0:
            self._on_step_continue()
            return

        self._step_timer_label.configure(
            text=f"Auto-continue in {self._step_countdown}s…"
        )
        self._step_timer_id = self.after(1000, self._tick_step_countdown)

    def _cancel_step_timer(self) -> None:
        """Cancel the auto-continue countdown if active."""
        if hasattr(self, "_step_timer_id"):
            self.after_cancel(self._step_timer_id)
            del self._step_timer_id

    def _on_step_continue(self) -> None:
        """Resume from step pause for one more event."""
        self._cancel_step_timer()
        self._step_paused = False
        self._destroy_step_frame()
        self._set_status(STATUS_RUNNING)
        self._status_label.configure(text_color=COLOR_SUCCESS)
        self._start_polling()

    def _update_progress(self, delivered: int = -1, total: int = -1) -> None:
        """Update sim progress label. Call with no args to reset."""
        if delivered < 0 or total <= 0:
            self._progress_label.configure(text="Progress: --/--")
        else:
            self._progress_label.configure(
                text=f"Progress: {delivered}/{total} packets")
