"""Canvas rendering: animation loop and all drawing routines."""

from config import (
    ANIMATION_INTERVAL_MS,
    MAX_REPLAY_FRAMES,
    PACKET_BOX_RATIO,
    PACKET_SPACING_RATIO,
    CANVAS_SENDER_Y_RATIO,
    CANVAS_RECV_Y_RATIO,
    CANVAS_MARGIN_RATIO,
    CANVAS_LABEL_X_RATIO,
    CANVAS_GRID_OFFSET_RATIO,
    CANVAS_FOOTER_RATIO,
    CANVAS_LEGEND_W_RATIO,
    COLOR_BG_HIGHLIGHT,
    COLOR_ACCENT,
    COLOR_SUCCESS,
    COLOR_ERROR,
    COLOR_WARNING,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    COLOR_BORDER,
    COLOR_UNSENT,
    COLOR_SENT,
    COLOR_ACKED,
    COLOR_TIMEOUT,
    MONO_FONT,
)


class CanvasRenderMixin:
    """Animation loop plus all canvas drawing methods."""

    def _start_animation(self) -> None:
        if not self._anim_active:
            self._anim_active = True
            self._schedule_animation()

    def _stop_animation(self) -> None:
        self._anim_active = False
        if self._anim_id:
            self.after_cancel(self._anim_id)
            self._anim_id = None

    def _schedule_animation(self) -> None:
        if not self._anim_active:
            return
        self._anim_frame += 1

        if self._replay_mode:
            self._playback_animation_frame()
        else:
            if self._slide_delay > 0:
                self._slide_delay -= 1
                if self._slide_delay == 0 and self._pending_snapshot is not None:
                    self._last_snapshot = self._pending_snapshot
                    self._pending_snapshot = None
            if self._replay_capturing:
                if len(self._replay_frames) < MAX_REPLAY_FRAMES:
                    self._replay_frames.append({
                        "anim_frame": self._anim_frame,
                        "snapshot": dict(self._last_snapshot) if self._last_snapshot else {},
                        "flights": {k: dict(v) for k, v in self._active_flights.items()},
                    })
            self._redraw_canvas()

        if self._anim_active:
            self._anim_id = self.after(
                ANIMATION_INTERVAL_MS, self._schedule_animation)

    def _redraw_canvas(self) -> None:
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()

        snap = self._last_snapshot
        if not snap:
            self._draw_placeholder()
            return

        new_size = (w, h)
        needs_static = new_size != self._canvas_size
        self._canvas_size = new_size
        if needs_static:
            self._canvas.delete("all")
        else:
            self._canvas.delete("dyn")

        s = self._s

        margin_left = int(w * CANVAS_MARGIN_RATIO)
        margin_right = int(w * CANVAS_MARGIN_RATIO)
        grid_start_x = margin_left + int(w * CANVAS_GRID_OFFSET_RATIO)
        label_x = int(w * CANVAS_LABEL_X_RATIO)

        sender_y = int(h * CANVAS_SENDER_Y_RATIO)
        mid_y = h / 2
        recv_y = int(h * CANVAS_RECV_Y_RATIO)

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

        box = int(w * PACKET_BOX_RATIO)
        gap = int(w * PACKET_SPACING_RATIO)
        slot_w = box + gap

        win_end = min(base + win_size, total)
        swin_visible = min(win_size, total - base)
        extra_ahead = 3
        shared_total = min(swin_visible + extra_ahead, total - base,
                           int((w - margin_left - margin_right) / slot_w))
        available_w = w - margin_left - margin_right
        min_box = int(w * PACKET_BOX_RATIO * 0.65)
        min_gap = int(w * PACKET_SPACING_RATIO * 1.5)
        if shared_total * slot_w > available_w:
            shared_slot = available_w / max(shared_total, 1)
            shared_box = max(min_box, shared_slot - min_gap)
            shared_font = max(7, int(shared_box // 3))
        else:
            shared_slot = slot_w
            shared_box = box
            shared_font = max(7, int(shared_box // 2.5))

        # === STATIC ELEMENTS (drawn once, only redrawn on resize) ===

        if needs_static:
            self._draw_neon_background(w, h)

            self._canvas.create_text(label_x, sender_y - int(30 * s),
                                     text="SENDER", anchor="w",
                                     fill=COLOR_ACCENT, font=(MONO_FONT, int(17 * s), "bold"))
            self._canvas.create_text(label_x, recv_y - int(24 * s),
                                     text="RECEIVER", anchor="w",
                                     fill=COLOR_SUCCESS, font=(MONO_FONT, int(17 * s), "bold"))

            self._canvas.create_line(0, mid_y, w, mid_y, fill="#4f46e5",
                                     dash=(6, 4), width=2)
            self._canvas.create_text(w // 2, mid_y - int(12 * s), text="CHANNEL",
                                     fill=COLOR_TEXT_MUTED, font=(MONO_FONT, int(10 * s)))

        sender_slot_x: dict[int, float] = {}

        for i in range(shared_total):
            pkt = base + i
            if pkt >= total:
                break
            x = grid_start_x + pkt * shared_slot

            if pkt in timed:
                color = COLOR_TIMEOUT
            elif pkt < base:
                color = COLOR_ACKED
            elif pkt in sent:
                color = COLOR_SENT
            else:
                color = COLOR_UNSENT

            self._draw_neon_box(x, sender_y, shared_box, color,
                                text=str(pkt), font=(MONO_FONT, shared_font, "bold"),
                                tags="dyn")
            sender_slot_x[pkt] = x + shared_box / 2

        if swin_visible > 0:
            is_resending = rw is not None
            if is_resending:
                pulse_phase = (self._anim_frame - rw_frame) % 6
                bracket_color = COLOR_ERROR if pulse_phase < 3 else COLOR_WARNING
                bracket_w = 3
            else:
                bracket_color = COLOR_ACCENT
                bracket_w = 2

            left_x = grid_start_x + base * shared_slot
            right_x = grid_start_x + \
                (base + swin_visible - 1) * shared_slot + shared_box

            self._canvas.create_line(left_x - int(5 * s), sender_y - int(12 * s),
                                     left_x - int(5 * s), sender_y + shared_box + int(12 * s),
                                     fill=bracket_color, width=bracket_w, tags="dyn")
            self._canvas.create_line(right_x + int(5 * s), sender_y - int(12 * s),
                                     right_x + int(5 * s), sender_y + shared_box + int(12 * s),
                                     fill=bracket_color, width=bracket_w, tags="dyn")
            self._canvas.create_line(left_x - int(5 * s), sender_y - int(12 * s),
                                     right_x + int(5 * s), sender_y - int(12 * s),
                                     fill=bracket_color, width=1, tags="dyn")

            label = f"N={win_size}"
            if is_resending:
                label += f"  [RESEND {rw[0]}..{rw[1]}]"
            self._canvas.create_text((left_x + right_x) / 2, sender_y - int(20 * s),
                                     text=label, fill=bracket_color,
                                     font=(MONO_FONT, int(9 * s), "bold"), tags="dyn")

        for pkt in range(base):
            x = grid_start_x + pkt * shared_slot
            if x + shared_box < grid_start_x:
                continue
            self._canvas.create_rectangle(
                x, sender_y, x + shared_box, sender_y + shared_box,
                fill=COLOR_ACKED, outline=COLOR_BORDER, width=1, stipple="gray50",
                tags="dyn",
            )
            self._canvas.create_text(
                x + shared_box / 2, sender_y + shared_box / 2,
                text=str(pkt), fill=COLOR_TEXT_MUTED,
                font=(MONO_FONT, shared_font, "bold"),
                tags="dyn",
            )
            sender_slot_x[pkt] = x + shared_box / 2

        recv_slot_x: dict[int, float] = {}
        recv_visible = min(shared_total, total - base)

        for i in range(recv_visible):
            pkt = base + i
            x = grid_start_x + pkt * shared_slot

            if pkt in received:
                self._canvas.create_rectangle(
                    x, recv_y, x + shared_box, recv_y + shared_box,
                    fill=COLOR_ACKED, outline=COLOR_BORDER, width=1,
                    stipple="gray50", tags="dyn",
                )
                self._canvas.create_text(
                    x + shared_box / 2, recv_y + shared_box / 2,
                    text=str(pkt), fill=COLOR_TEXT_MUTED,
                    font=(MONO_FONT, shared_font, "bold"),
                    tags="dyn",
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
                                text=str(pkt), font=(MONO_FONT, shared_font, "bold"),
                                tags="dyn")
            recv_slot_x[pkt] = x + shared_box / 2

        for pkt in range(min(base, total)):
            if pkt in received:
                x = grid_start_x + pkt * shared_slot
                if x + shared_box < grid_start_x:
                    continue
                self._canvas.create_rectangle(
                    x, recv_y, x + shared_box, recv_y + shared_box,
                    fill=COLOR_ACKED, outline=COLOR_BORDER, width=1,
                    stipple="gray50", tags="dyn",
                )
                self._canvas.create_text(
                    x + shared_box / 2, recv_y + shared_box / 2,
                    text=str(pkt), fill=COLOR_TEXT_MUTED,
                    font=(MONO_FONT, shared_font, "bold"),
                    tags="dyn",
                )
                recv_slot_x[pkt] = x + shared_box / 2

        if self._active_flights:
            dot_r = max(4, int(w * PACKET_BOX_RATIO * 0.26))
            flight_frames = max(self._FLIGHT_FRAMES, 1)
            fail_disp = self._FAIL_DISPLAY_FRAMES
            fail_point = self._FAIL_POINT

            occupied: dict[tuple[int, int], int] = {}

            for flight_id, flight in list(self._active_flights.items()):
                elapsed = self._anim_frame - flight["start_frame"]
                direction = flight["direction"]
                result = flight.get("result", "ok")
                is_failure = result in ("lost", "corrupt")

                if is_failure:
                    progress = min(elapsed / flight_frames, fail_point)
                    failed_at = flight.get("failed_at", self._anim_frame)
                    fail_elapsed = self._anim_frame - failed_at
                    if fail_elapsed > fail_disp:
                        del self._active_flights[flight_id]
                        continue
                else:
                    landed = flight.get("landing_frames", 0)
                    if landed > 0:
                        flight["landing_frames"] = landed - 1
                        progress = 1.0
                    else:
                        progress = min(elapsed / flight_frames, 1.0)
                        if progress >= 1.0:
                            del self._active_flights[flight_id]
                            continue

                display_pkt = -flight_id - 1 if flight_id < 0 else flight_id

                if direction == "ack":
                    recv_col = display_pkt - base
                    if recv_col >= 0 and display_pkt in recv_slot_x:
                        start_x = recv_slot_x[display_pkt]
                    elif display_pkt < base:
                        start_x = grid_start_x + dot_r + 4
                    else:
                        start_x = w - margin_right - dot_r

                    if display_pkt in sender_slot_x:
                        end_x = sender_slot_x[display_pkt]
                    elif display_pkt < base:
                        end_x = grid_start_x + dot_r + 4
                    else:
                        end_x = w - margin_right - dot_r
                else:
                    sender_col = display_pkt - base
                    if sender_col >= 0 and display_pkt in sender_slot_x:
                        start_x = sender_slot_x[display_pkt]
                    elif sender_col < 0:
                        start_x = grid_start_x + dot_r + 4
                    else:
                        start_x = w - margin_right - dot_r

                    if display_pkt in recv_slot_x:
                        end_x = recv_slot_x[display_pkt]
                    else:
                        end_x = grid_start_x + display_pkt * shared_slot + shared_box / 2

                t = progress
                ease = t * t * (3 - 2 * t)
                x = start_x + ease * (end_x - start_x)
                x = max(grid_start_x + dot_r, min(x, w - margin_right - dot_r))

                top_y = sender_y + shared_box + dot_r
                bot_y = recv_y - dot_r

                if direction in ("send", "resend"):
                    y = top_y + ease * (bot_y - top_y)
                else:
                    y = bot_y - ease * (bot_y - top_y)

                grid_key = (int(x / (dot_r * 2)), int(y / (dot_r * 2)))
                same_spot = occupied.get(grid_key, 0)
                if same_spot > 0:
                    stagger_dx = (same_spot % 3 - 1) * dot_r * 2
                    stagger_dy = ((same_spot // 3) % 3 - 1) * dot_r * 2
                    x += stagger_dx
                    y += stagger_dy
                occupied[grid_key] = same_spot + 1

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

                r = dot_r
                hw = int(r * 0.8)
                body_end = int(r * 0.7)

                if direction == "ack":
                    body = [
                        x, y - r,
                        x - hw, y + body_end,
                        x - int(hw * 0.35), y + body_end,
                        x - int(hw * 0.35), y + r,
                        x + int(hw * 0.35), y + r,
                        x + int(hw * 0.35), y + body_end,
                        x + hw, y + body_end,
                    ]
                else:
                    body = [
                        x, y + r,
                        x - hw, y - body_end,
                        x - int(hw * 0.35), y - body_end,
                        x - int(hw * 0.35), y - r,
                        x + int(hw * 0.35), y - r,
                        x + int(hw * 0.35), y - body_end,
                        x + hw, y - body_end,
                    ]

                outline_color = COLOR_ERROR if is_failure else "#a5b4fc"
                self._canvas.create_polygon(
                    *body, fill=fill, outline=outline_color, width=1, tags="dyn"
                )

                if not is_failure:
                    if direction == "ack":
                        self._canvas.create_line(
                            x, y + r, x, y - int(r * 0.3),
                            fill="#6b7280", width=1, tags="dyn"
                        )
                    else:
                        self._canvas.create_line(
                            x, y - r, x, y + int(r * 0.3),
                            fill="#6b7280", width=1, tags="dyn"
                        )

                if is_failure:
                    self._canvas.create_text(
                        x, y, text="✗",
                        fill=COLOR_ERROR, font=(MONO_FONT, max(8, int(12 * s)), "bold"),
                        tags="dyn"
                    )
                else:
                    label = f"#{display_pkt}" if flight_id >= 0 else f"ACK{display_pkt}"
                    label_y = y + r + int(10 * s) if direction == "ack" else y - r - int(10 * s)
                    self._canvas.create_text(
                        x, label_y, text=label,
                        fill=fill, font=(MONO_FONT, max(5, int(8 * s))), tags="dyn"
                    )

        delivered = snap.get("delivered", 0)
        sent_count = len(sent)
        footer_y = recv_y + shared_box + int(h * CANVAS_FOOTER_RATIO)
        self._canvas.create_text(label_x, footer_y,
                                 text=f"Delivered: {delivered}/{total}  |  "
                                 f"Sent (unACKed): {sent_count}",
                                 anchor="w", fill=COLOR_TEXT_MUTED,
                                 font=(MONO_FONT, int(15 * s)), tags="dyn")

        if needs_static:
            lx = w - margin_right - int(w * CANVAS_LEGEND_W_RATIO)
            items = [
                (COLOR_SENT, "Sent / UnACKed"),
                (COLOR_ACKED, "ACKed / Received"),
                (COLOR_TIMEOUT, "Timed out / Corrupt"),
                (COLOR_UNSENT, "Not yet sent"),
            ]
            for i, (c, lbl) in enumerate(items):
                y = footer_y + i * int(18 * s)
                sw = int(10 * s)
                self._canvas.create_rectangle(
                    lx, y, lx + sw, y + sw, fill=c, outline="")
                self._canvas.create_text(lx + sw + int(6 * s), y + sw / 2,
                                         text=lbl, anchor="w",
                                         fill=COLOR_TEXT_MUTED,
                                         font=(MONO_FONT, int(10 * s)))

    def _draw_neon_background(self, w: int, h: int) -> None:
        s = self._s
        for i in range(3):
            r = int((50 + i * 30) * s)
            alpha = 3 - i
            cx, cy = w // 2, h // 2
            self._canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                     fill="", outline="#6366f1",
                                     width=1, dash=(1, alpha * 4))

    def _draw_neon_box(self, x: float, y: float, size: float, fill: str,
                       outline: str = "", text: str = "", text_color: str = "",
                       font=(MONO_FONT, 9, "bold"), pulse: bool = False,
                       tags: str = "") -> None:
        self._canvas.create_rectangle(
            x, y, x + size, y + size,
            fill=fill, outline="#a5b4fc", width=2, tags=tags,
        )
        if text:
            self._canvas.create_text(
                x + size / 2, y + size / 2,
                text=text, fill=text_color or COLOR_TEXT,
                font=font, tags=tags,
            )

    def _draw_placeholder(self) -> None:
        try:
            w = self._canvas.winfo_width()
            h = self._canvas.winfo_height()
        except Exception:
            return
        if w < 100 or h < 100:
            self.after(200, self._draw_placeholder)
            return
        self._canvas.delete("all")
        self._canvas_size = (0, 0)
        font_size = max(10, int(14 * self._s))
        self._canvas.create_text(w // 2, h // 2,
                                 text="Click 'Start Simulation'\nto begin",
                                 fill=COLOR_TEXT_MUTED, font=(MONO_FONT, font_size),
                                 justify="center")
