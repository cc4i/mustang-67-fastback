"""Voice pipeline telemetry & `S1`–`S7` evaluation ledger (`metrics.py`)."""

from __future__ import annotations

import json
import pathlib
import statistics
import time
from dataclasses import asdict, dataclass, field
from typing import Any


from mustang_ai.config import resolve_repo_root


@dataclass
class VoiceMetricsLedger:
    """Tracks real-time voice metrics and evaluates pass/fail against Milestone A criteria `S1`–`S7`."""

    ledger_path: pathlib.Path | None = None
    self_trigger_count: int = 0
    echo_frames_tested: int = 0
    erle_samples_db: list[float] = field(default_factory=list)
    false_wake_on_motor_noise: int = 0
    motor_noise_frames_tested: int = 0
    noisy_wake_attempts: int = 0
    noisy_wake_hits: int = 0
    ttfa_samples_ms: list[float] = field(default_factory=list)
    barge_in_latencies_ms: list[float] = field(default_factory=list)
    stop_latencies_ms: list[float] = field(default_factory=list)
    follow_up_turns_completed: int = 0
    conversations_reset_at_idle: int = 0
    duplicate_cloud_moves_filtered: int = 0
    offline_fallbacks_triggered: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.ledger_path is None:
            default_dir = resolve_repo_root() / "tmp"
            default_dir.mkdir(parents=True, exist_ok=True)
            self.ledger_path = default_dir / "voice_metrics_ledger.jsonl"

    def record_event(self, event_type: str, **payload: Any) -> dict[str, Any]:
        """Append a structured telemetry event to memory and `tmp/voice_metrics_ledger.jsonl`."""
        entry = {
            "timestamp_s": round(time.time(), 4),
            "event_type": event_type,
            **payload,
        }
        self.events.append(entry)
        if len(self.events) > 250:
            del self.events[: len(self.events) - 250]
        if self.ledger_path is not None:
            try:
                self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
                with self.ledger_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry) + "\n")
            except OSError:
                pass
        return entry

    def summary_report(self) -> dict[str, Any]:
        """Compute `S1`–`S7` pass/fail summary and percentile metrics."""
        mean_erle_db = round(statistics.fmean(self.erle_samples_db), 2) if self.erle_samples_db else 0.0
        wake_hit_rate = (
            round(self.noisy_wake_hits / float(self.noisy_wake_attempts), 4)
            if self.noisy_wake_attempts > 0
            else 1.0
        )
        sorted_ttfa = sorted(self.ttfa_samples_ms)
        ttfa_p50 = round(sorted_ttfa[len(sorted_ttfa) // 2], 2) if sorted_ttfa else 0.0
        ttfa_p90_idx = min(len(sorted_ttfa) - 1, int(len(sorted_ttfa) * 0.90)) if sorted_ttfa else 0
        ttfa_p90 = round(sorted_ttfa[ttfa_p90_idx], 2) if sorted_ttfa else 0.0
        max_barge_ms = round(max(self.barge_in_latencies_ms), 2) if self.barge_in_latencies_ms else 0.0
        max_stop_ms = round(max(self.stop_latencies_ms), 2) if self.stop_latencies_ms else 0.0

        s1_pass = self.self_trigger_count == 0 and (not self.erle_samples_db or mean_erle_db >= 15.0)
        s2_pass = self.false_wake_on_motor_noise == 0
        s3_pass = wake_hit_rate >= 0.90
        s4_pass = not sorted_ttfa or (ttfa_p50 <= 2000.0 and ttfa_p90 <= 3000.0)
        s5_pass = not self.barge_in_latencies_ms or max_barge_ms <= 200.0
        s6_pass = not self.stop_latencies_ms or max_stop_ms <= 100.0
        s7_pass = (
            (self.follow_up_turns_completed == 0 and self.conversations_reset_at_idle == 0 and not sorted_ttfa)
            or (self.follow_up_turns_completed >= 1 and self.conversations_reset_at_idle >= 1)
        )

        gates = {
            "S1_zero_self_triggers_and_erle_15db": {
                "passed": s1_pass,
                "self_triggers": self.self_trigger_count,
                "mean_erle_db": mean_erle_db,
            },
            "S2_zero_false_wake_on_motor_noise": {
                "passed": s2_pass,
                "false_wake_triggers": self.false_wake_on_motor_noise,
                "motor_noise_frames_tested": self.motor_noise_frames_tested,
            },
            "S3_wake_and_command_under_motor_noise": {
                "passed": s3_pass,
                "wake_hit_rate": wake_hit_rate,
                "hits": self.noisy_wake_hits,
                "attempts": self.noisy_wake_attempts,
            },
            "S4_ttfa_p50_2s_p90_3s": {
                "passed": s4_pass,
                "ttfa_p50_ms": ttfa_p50,
                "ttfa_p90_ms": ttfa_p90,
            },
            "S5_barge_in_cut_le_200ms": {
                "passed": s5_pass,
                "max_barge_in_latency_ms": max_barge_ms,
            },
            "S6_local_stop_le_100ms": {
                "passed": s6_pass,
                "max_stop_latency_ms": max_stop_ms,
            },
            "S7_follow_up_8s_and_idle_memory_reset": {
                "passed": s7_pass,
                "follow_up_turns_completed": self.follow_up_turns_completed,
                "conversations_reset_at_idle": self.conversations_reset_at_idle,
            },
        }
        all_passed = all(g["passed"] for g in gates.values())
        return {
            "status": "PASS" if all_passed else "FAIL",
            "all_s1_s7_passed": all_passed,
            "gates": gates,
            "duplicate_cloud_moves_filtered": self.duplicate_cloud_moves_filtered,
            "offline_fallbacks_triggered": self.offline_fallbacks_triggered,
            "raw_counts": {
                k: v
                for k, v in asdict(self).items()
                if k not in ("events", "ledger_path", "erle_samples_db", "ttfa_samples_ms")
            },
        }
