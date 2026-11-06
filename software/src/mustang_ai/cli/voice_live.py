"""CLI entrypoint (`mustang_ai.cli.voice_live`) for Milestone A (`make voice-live`).

Runs the `S1`–`S7` + `D1`–`D15` pre-flight voice pipeline verification suite (measuring WebRTC `AEC3`
`ERLE dB`, `0` self-triggers, `0` false wakes on motor noise, noisy wake-word hit rate, `TTFA`,
`<= 200 ms` barge-in cut, `<= 100 ms` local `"stop"`, and `8.0 s` `FOLLOW_UP` + `IDLE` memory reset),
writes `tmp/milestone_a_voice_report.json`, and launches the interactive Workbench (`http://127.0.0.1:8765`)
unless `--verify-only` is passed.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Sequence

from mustang_ai.simulator.mac_live_workbench import serve_live_workbench
from mustang_ai.voice.conversation import run_s1_s7_verification_suite


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mustang-ai voice-live",
        description="Milestone A Laptop-First Radxa Voice Stack (AEC3 + NS + Wake Word + Barge-In + State Machine).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Localhost interface to bind (must be 127.0.0.1 or localhost).")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port for the interactive workbench.")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open browser tab.")
    parser.add_argument("--mute", action="store_true", help="Mute physical laptop speaker playback.")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Run S1..S7 + D1..D15 verification suite, write tmp/milestone_a_voice_report.json, and exit.",
    )
    parser.add_argument(
        "--real-piper",
        action="store_true",
        help="Use LocalPiperTTS (en_US-amy-low.onnx) during the S1..S7 verification suite.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    # Security: enforce localhost-only binding
    bind_host = args.host if args.host in ("127.0.0.1", "localhost") else "127.0.0.1"

    report = run_s1_s7_verification_suite(use_real_piper=args.real_piper)
    repo_root = pathlib.Path(__file__).resolve().parents[4]
    report_path = repo_root / "tmp" / "milestone_a_voice_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.verify_only:
        print(json.dumps(report, indent=2))
        return 0 if report.get("status") == "PASS" else 1

    print(
        f"Milestone A Voice Pipeline Pre-Flight: {report.get('status')} "
        f"(ERLE={report['gates']['S1_zero_self_triggers_and_erle_15db']['mean_erle_db']} dB, "
        f"SelfTriggers={report['gates']['S1_zero_self_triggers_and_erle_15db']['self_triggers']}, "
        f"MotorFalseWakes={report['gates']['S2_zero_false_wake_on_motor_noise']['false_wake_triggers']})"
    )
    serve_live_workbench(
        host=bind_host,
        port=args.port,
        open_browser=not args.no_browser,
        audible_speaker=not args.mute,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
