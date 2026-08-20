"""Go-Back-N ARQ Protocol — Simulation Engine."""

from __future__ import annotations

import heapq
import queue
import random
import threading
import time as _time
from dataclasses import dataclass, field
from typing import Optional


class EventType:
    PACKET_SENT = "PACKET_SENT"
    PACKET_RECEIVED = "PACKET_RECEIVED"
    PACKET_CORRUPTED = "PACKET_CORRUPTED"
    PACKET_LOST = "PACKET_LOST"
    ACK_SENT = "ACK_SENT"
    ACK_RECEIVED = "ACK_RECEIVED"
    ACK_CORRUPTED = "ACK_CORRUPTED"
    ACK_LOST = "ACK_LOST"
    TIMEOUT = "TIMEOUT"


@dataclass(order=True)
class SimEvent:
    """A discrete event in the simulation timeline, ordered by time."""
    time: float
    priority: int = 50
    type: str = EventType.PACKET_SENT
    packet_id: int = -1
    ack_id: int = -1
    meta: dict = field(default_factory=dict, compare=False)


class Channel:
    """Simulates a noisy communication channel with BER and packet loss."""

    def __init__(self, ber: float = 0.0, packet_loss: float = 0.0,
                 propagation_delay_ms: float = 10.0, data_rate_kbps: float = 100.0):
        self.ber = max(0.0, min(1.0, ber))
        self.packet_loss = max(0.0, min(1.0, packet_loss))
        self.propagation_delay_ms = propagation_delay_ms
        self.data_rate_kbps = data_rate_kbps
        self.packets_through = 0
        self.corrupted = 0
        self.lost = 0

    def transmit(self, size_bits: int) -> tuple[bool, bool, float]:
        """Simulate transmission through the channel.

        Returns:
            (corrupted: bool, lost: bool, tx_time_ms: float)
        """
        self.packets_through += 1

        if random.random() < self.packet_loss:
            self.lost += 1
            tx_time = size_bits / max(self.data_rate_kbps, 0.001)
            return False, True, tx_time

        corrupted = False
        if self.ber > 0:
            success_prob = (1.0 - self.ber) ** size_bits
            if random.random() > success_prob:
                corrupted = True
                self.corrupted += 1

        tx_time = size_bits / max(self.data_rate_kbps, 0.001)
        return corrupted, False, tx_time

    def one_way_ms(self, size_bits: int = 0) -> float:
        return (size_bits / max(self.data_rate_kbps, 0.001)) + self.propagation_delay_ms

    def reset(self) -> None:
        self.packets_through = 0
        self.corrupted = 0
        self.lost = 0


class GBNState:
    """Snapshot of the Go-Back-N sender and receiver at a given moment."""
    def __init__(self):
        self.base: int = 0
        self.next_seq: int = 0
        self.sent: set = set()
        self.timed_out: set = set()

        self.expected: int = 0
        self.received: set = set()
        self.corrupted: set = set()

        self.retransmitting_window: tuple | None = None
        self.retransmit_frame: int = 0



class GBNSimulation:
    """Go-Back-N simulation engine. Runs in a background thread.

    Call poll() periodically from the GUI thread for events and snapshots.
    """

    def __init__(self, *, window_size: int = 4, ber: float = 0.0001,
                 packet_loss: float = 0.0, num_packets: int = 40,
                 timeout_ms: float = 300.0, packet_size_bits: int = 1000,
                 data_rate_kbps: float = 100.0, propagation_delay_ms: float = 10.0,
                 sim_speed: float = 1.0):
        self.window_size = window_size
        self.num_packets = num_packets
        self.packet_size_bits = packet_size_bits
        self.timeout_ms = timeout_ms
        self.data_rate_kbps = data_rate_kbps
        self.propagation_delay_ms = propagation_delay_ms
        self.sim_speed = max(0.1, min(50.0, sim_speed))

        self.channel = Channel(ber=ber, packet_loss=packet_loss,
                               propagation_delay_ms=propagation_delay_ms,
                               data_rate_kbps=data_rate_kbps)

        self.state = GBNState()
        self.delivered = 0
        self.total_sent = 0
        self.retransmissions = 0
        self.acks_sent = 0
        self.timeouts = 0
        self.errors = 0
        self.start_time = 0.0
        self.end_time = 0.0
        self.total_delay = 0.0

        self._event_heap: list[SimEvent] = []
        self._msg_queue: queue.Queue = queue.Queue(maxsize=300)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._sim_time: float = 0.0
        self._running = False
        self._event_count: int = 0

        self._timeout_pending: bool = False

        self._ack_slot: float = 0.0

    @property
    def _timer_ms(self) -> float:
        """Adaptive timeout: 3× estimated RTT, capped by the user slider.

        The window retransmits quickly when no ACK arrives (slide back),
        but the user can set an even shorter cap via the timeout slider.
        """
        rtt = 2 * self.propagation_delay_ms + self._tx_time_ms
        computed = rtt * 3
        return min(self.timeout_ms, computed) if self.timeout_ms > 0 else computed

    @property
    def running(self) -> bool:
        return self._running

    @property
    def metrics(self) -> dict:
        """Return final performance metrics (valid after completion)."""
        duration = self.end_time - self.start_time
        if duration <= 0:
            return {"throughput_bps": 0, "efficiency": 0, "retransmissions": 0,
                    "timeouts": 0, "errors": 0, "avg_delay_ms": 0,
                    "delivered": self.delivered, "total_sent": self.total_sent}

        bits_delivered = self.delivered * self.packet_size_bits
        throughput = bits_delivered / (duration / 1000.0)
        efficiency = self.delivered / max(self.total_sent, 1)
        avg_delay = self.total_delay / max(self.delivered, 1)

        return {
            "throughput_bps": throughput,
            "efficiency": efficiency,
            "retransmissions": self.retransmissions,
            "timeouts": self.timeouts,
            "errors": self.errors,
            "avg_delay_ms": avg_delay,
            "delivered": self.delivered,
            "total_sent": self.total_sent,
            "duration_ms": duration,
        }

    def start(self) -> None:
        """Launch the simulation in a background thread."""
        if self._running:
            return
        self._stop.clear()
        self._running = True
        self._sim_time = 0.0

        self._next_send_slot = 1.0
        self._ack_slot = 1.0

        initial_count = min(self.window_size, self.num_packets)
        for i in range(initial_count):
            heapq.heappush(self._event_heap, self._make_send_event(i))
            self.state.sent.add(i)

        self.state.next_seq = initial_count

        self._state_to_queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the simulation."""
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._running = False

    def poll(self, max_msgs: int = 15) -> list[dict]:
        """Drain up to max_msgs from the queue. Call from GUI thread periodically."""
        msgs: list[dict] = []
        for _ in range(max_msgs):
            try:
                msgs.append(self._msg_queue.get_nowait())
            except queue.Empty:
                break
        return msgs

    def _run(self) -> None:
        """Main event loop, runs in background thread with rate-limiting.

        Events at the same sim-time are emitted together so the initial
        send burst fires in rapid succession — multiple packets appear
        in-flight simultaneously like a real GBN pipeline.
        """
        while not self._stop.is_set() and self._event_heap:
            # Process all events at the current earliest sim-time together
            now = self._event_heap[0].time
            while self._event_heap and self._event_heap[0].time <= now:
                event = heapq.heappop(self._event_heap)
                self._sim_time = event.time
                self._event_count += 1

                new = self._step(event)
                for evt in new:
                    if evt.time < self._sim_time:
                        evt.time = self._sim_time + 0.001
                    heapq.heappush(self._event_heap, evt)

                self._emit({"type": "event", "event": event,
                            "state_snapshot": self._make_snapshot()})

                if self.delivered >= self.num_packets:
                    break

            if self.delivered >= self.num_packets:
                self.end_time = self._sim_time
                self._drain_ack_events()
                self._emit({"type": "done", "metrics": self.metrics})
                self._running = False
                return

            _time.sleep(0.08 / self.sim_speed)

        if self.delivered >= self.num_packets:
            self.end_time = self._sim_time
            self._emit({"type": "done", "metrics": self.metrics})
        self._running = False

    def _drain_ack_events(self, max_iter: int = 50) -> None:
        """Emit remaining ACK events so the GUI shows the final acknowledgments.

        After all data packets are delivered, the receiver's final ACK
        may still be in the heap (ACK_SENT at receiver → ACK_RECEIVED at
        sender).  Emit them as regular events so the user sees the
        simulation wrap up cleanly.
        """
        ack_types = {EventType.ACK_SENT, EventType.ACK_RECEIVED,
                     EventType.ACK_LOST, EventType.ACK_CORRUPTED}
        for _ in range(max_iter):
            if not self._event_heap:
                break
            event = self._event_heap[0]
            if event.type not in ack_types:
                break
            heapq.heappop(self._event_heap)
            self._sim_time = event.time
            new = self._step(event)
            for evt in new:
                if evt.time < self._sim_time:
                    evt.time = self._sim_time + 0.001
                heapq.heappush(self._event_heap, evt)

            self._emit({"type": "event", "event": event, "state_snapshot": self._make_snapshot()})

            _time.sleep(0.08 / self.sim_speed)

    def _step(self, event: SimEvent) -> list[SimEvent]:
        """Route an event to the appropriate handler."""
        et = event.type
        if et == EventType.PACKET_SENT:
            return self._on_packet_sent(event)
        elif et == EventType.PACKET_RECEIVED:
            return self._on_packet_received(event)
        elif et in (EventType.PACKET_CORRUPTED, EventType.PACKET_LOST):
            return self._on_packet_dropped(event)
        elif et == EventType.ACK_SENT:
            return self._on_ack_sent(event)
        elif et == EventType.ACK_RECEIVED:
            return self._on_ack_received(event)
        elif et in (EventType.ACK_CORRUPTED, EventType.ACK_LOST):
            return []
        elif et == EventType.TIMEOUT:
            return self._on_timeout(event)
        return []


    def _on_packet_sent(self, event: SimEvent) -> list[SimEvent]:
        out = []
        pid = event.packet_id

        if self.total_sent == 0:
            self.start_time = event.time
        self.total_sent += 1

        self.state.sent.add(pid)

        corrupted, lost, tx_time = self.channel.transmit(self.packet_size_bits)
        arrival = event.time + tx_time + self.channel.propagation_delay_ms

        if lost:
            self.errors += 1
            self.state.corrupted.add(pid)
            out.append(SimEvent(arrival, type=EventType.PACKET_LOST, packet_id=pid))
        elif corrupted:
            self.errors += 1
            self.state.corrupted.add(pid)
            out.append(SimEvent(arrival, type=EventType.PACKET_CORRUPTED, packet_id=pid))
        else:
            out.append(SimEvent(arrival, type=EventType.PACKET_RECEIVED, packet_id=pid))

        if not self._timeout_pending and pid == self.state.base:
            self._timeout_pending = True
            out.append(SimEvent(event.time + self._timer_ms,
                                type=EventType.TIMEOUT, packet_id=pid))

        self.state.next_seq = max(self.state.next_seq, pid + 1)

        return out

    def _on_packet_received(self, event: SimEvent) -> list[SimEvent]:
        out = []
        pid = event.packet_id
        s = self.state

        if pid == s.expected:
            self.delivered += 1
            delay = event.time - max(self.start_time, 0)
            self.total_delay += delay
            s.received.add(pid)
            s.expected += 1
            s.corrupted.discard(pid)

            event.meta["accepted"] = True

            ack = s.expected - 1
            floor = event.time + 0.5
            if self._ack_slot < floor:
                self._ack_slot = floor
            ack_send_time = self._ack_slot
            self._ack_slot += max(self._tx_time_ms * 0.1, 0.5)
            ack_time = ack_send_time + self.channel.propagation_delay_ms
            out.append(SimEvent(ack_time, type=EventType.ACK_SENT,
                                ack_id=ack, packet_id=pid,
                                meta={"from_accept": True}))
            self.acks_sent += 1
        else:
            event.meta["accepted"] = False
            event.meta["expected"] = s.expected

        return out

    def _on_packet_dropped(self, event: SimEvent) -> list[SimEvent]:
        """Packet was corrupted or lost at the receiver — drop silently.

        No duplicate ACK is sent; the sender recovers via timeout.
        """
        return []

    def _on_ack_sent(self, event: SimEvent) -> list[SimEvent]:
        """ACK sent from receiver — transmit back through channel."""
        out = []
        corrupted, lost, tx_time = self.channel.transmit(40)
        arrival = event.time + tx_time + self.channel.propagation_delay_ms

        if lost:
            self.errors += 1
            out.append(SimEvent(arrival, type=EventType.ACK_LOST, ack_id=event.ack_id))
        elif corrupted:
            self.errors += 1
            out.append(SimEvent(arrival, type=EventType.ACK_CORRUPTED, ack_id=event.ack_id))
        else:
            out.append(SimEvent(arrival, type=EventType.ACK_RECEIVED, ack_id=event.ack_id))
        return out

    def _on_ack_received(self, event: SimEvent) -> list[SimEvent]:
        """Sender receives a cumulative ACK — slide the window."""
        out = []
        ack = event.ack_id
        old_base = self.state.base

        if ack >= self.state.base:
            self.state.base = ack + 1
            self.state.next_seq = max(self.state.next_seq, self.state.base)

            self._timeout_pending = False
            if self.state.base > old_base:

                self._event_heap = [e for e in self._event_heap
                                    if e.type != EventType.TIMEOUT]
                heapq.heapify(self._event_heap)


            self.state.sent = {p for p in self.state.sent if p > ack}
            self.state.timed_out = {t for t in self.state.timed_out if t > ack}

            rw = self.state.retransmitting_window
            if rw and self.state.base > rw[1]:
                self.state.retransmitting_window = None

            while self.state.next_seq < self.state.base + self.window_size \
                  and self.state.next_seq < self.num_packets:
                out.append(self._make_send_event(self.state.next_seq))
                self.state.sent.add(self.state.next_seq)
                self.state.next_seq += 1

            if self.state.base < self.state.next_seq and not self._timeout_pending:
                self._timeout_pending = True
                out.append(SimEvent(self._sim_time + self._timer_ms,
                                    type=EventType.TIMEOUT,
                                    packet_id=self.state.base))
        else:
            event.meta["is_duplicate"] = True

        return out

    def _on_timeout(self, event: SimEvent) -> list[SimEvent]:
        out = []

        if event.packet_id < self.state.base:
            return out

        self.timeouts += 1
        self._timeout_pending = False
        self.state.timed_out.add(event.packet_id)

        win_start = self.state.base
        win_end = min(self.state.next_seq - 1, self.num_packets - 1)

        stale_packet_types = {
            EventType.PACKET_RECEIVED,
            EventType.PACKET_CORRUPTED,
            EventType.PACKET_LOST,
        }
        stale_ack_types = {EventType.ACK_SENT, EventType.ACK_RECEIVED}
        recv_expected = self.state.expected

        keep = []
        for e in self._event_heap:
            if e.type == EventType.TIMEOUT:
                continue
            if e.type in stale_packet_types and win_start <= e.packet_id <= win_end:
                continue
            if e.type in stale_ack_types and e.ack_id < recv_expected:
                continue
            keep.append(e)
        self._event_heap = keep
        heapq.heapify(self._event_heap)

        event.meta = {
            "window_start": win_start,
            "window_end": win_end,
            "window_size": self.window_size,
        }

        self.state.retransmitting_window = (win_start, win_end)
        self.state.retransmit_frame += 1

        self._next_send_slot = max(self._next_send_slot, self._sim_time + 5.0)
        for pid in range(win_start, win_end + 1):
            if pid < self.num_packets:
                self.retransmissions += 1
                self.state.sent.add(pid)
                out.append(self._make_send_event(pid))

        return out


    @property
    def _tx_time_ms(self) -> float:
        """Transmission time for one packet in milliseconds."""
        return self.packet_size_bits / self.data_rate_kbps

    def _make_send_event(self, pkt_id: int) -> SimEvent:
        
        floor = self._sim_time + 1.0
        if self._next_send_slot < floor:
            self._next_send_slot = floor
        t = self._next_send_slot
        self._next_send_slot += self._tx_time_ms
        return SimEvent(t, type=EventType.PACKET_SENT, packet_id=pkt_id)

    def _make_snapshot(self) -> dict:
        s = self.state
        win_end = min(s.base + self.window_size, self.num_packets)
        rw = s.retransmitting_window
        return {
            "sim_time": self._sim_time,
            "sender": {
                "base": s.base,
                "next_seq": s.next_seq,
                "window_size": self.window_size,
                "window": list(range(s.base, win_end)),
                "sent": sorted(s.sent),
                "timed_out": sorted(s.timed_out),
                "retransmitting_window": list(rw) if rw else None,
                "retransmit_frame": s.retransmit_frame,
            },
            "receiver": {
                "expected": s.expected,
                "received": sorted(s.received),
                "corrupted": sorted(s.corrupted),
            },
            "num_packets": self.num_packets,
            "delivered": self.delivered,
        }

    def _emit(self, msg: dict) -> None:
        try:
            self._msg_queue.put(msg, timeout=0.5)
        except queue.Full:
            pass  
    def _state_to_queue(self) -> None:
        self._emit({"type": "tick", "state_snapshot": self._make_snapshot()})
