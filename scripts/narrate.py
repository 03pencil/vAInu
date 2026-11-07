"""Batch narration of pilot alarms with the local LLM (advisory text only).

Usage:
    .venv/bin/python scripts/narrate.py --check              # is Ollama up and the model installed?
    .venv/bin/python scripts/narrate.py --dry-run            # show what would be sent, no writes
    .venv/bin/python scripts/narrate.py                      # narrate new watch/alarm records
    .venv/bin/python scripts/narrate.py --template-only      # deterministic text, no model
    .venv/bin/python scripts/narrate.py --force              # narrate again even if done before

Reads <pilot>/state.json and <pilot>/predictions.jsonl and writes one line per
narration to <pilot>/analysis.jsonl. Nothing else is modified. Re-running is
safe: records that already have a narration are skipped. Settings come from
the [llm] section of config.toml; command-line flags override them.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import get_data_dir, get_llm_config  # noqa: E402
from src.narration import (  # noqa: E402
    LlmError,
    OllamaClient,
    build_prompt,
    plan_narrations,
    run_plan,
    situation_report,
    SYSTEM_PROMPT,
)

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pilot-dir", default=str(ROOT / "pilot"),
                        help="Directory with state.json and predictions.jsonl (default: pilot/).")
    parser.add_argument("--data", default=None,
                        help="Tier directory for events and maintenance history; defaults to [paths] data_dir.")
    parser.add_argument("--out", default=None,
                        help="Analysis file (default: <pilot-dir>/analysis.jsonl).")
    parser.add_argument("--base-url", default=None, help="Ollama URL (default from [llm]).")
    parser.add_argument("--model", default=None, help="Model tag (default from [llm]).")
    parser.add_argument("--timeout", type=float, default=None, help="Seconds per request.")
    parser.add_argument("--retries", type=int, default=None, help="Extra attempts after a rejected answer.")
    parser.add_argument("--max-records", type=int, default=None, help="Most records per run.")
    parser.add_argument("--template-only", action="store_true",
                        help="Write template text without calling the model.")
    parser.add_argument("--force", action="store_true",
                        help="Narrate records even when a narration already exists.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the reports that would be sent; write nothing.")
    parser.add_argument("--check", action="store_true",
                        help="Check that the model server and model are available, then exit.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = get_llm_config()
    base_url = args.base_url or cfg["base_url"]
    model = args.model or cfg["model"]
    timeout = args.timeout or float(cfg["timeout_seconds"])
    retries = args.retries if args.retries is not None else int(cfg["retries"])
    max_records = args.max_records or int(cfg["max_records_per_run"])
    pilot_dir = Path(args.pilot_dir)
    out_path = Path(args.out) if args.out else pilot_dir / "analysis.jsonl"
    data_path = args.data or get_data_dir()

    use_llm = bool(cfg["enabled"]) and not args.template_only and not args.dry_run
    if not args.template_only and not cfg["enabled"] and not args.dry_run and not args.check:
        print("[llm] enabled = false in config.toml: writing template text only.")
    client = OllamaClient(base_url, model, timeout, int(cfg["max_tokens"])) if use_llm else None

    if args.check:
        probe = OllamaClient(base_url, model, timeout, int(cfg["max_tokens"]))
        try:
            probe.check_model()
        except LlmError as exc:
            print(f"FAILED: {exc}")
            return 2
        print(f"OK: {model} is available at {base_url}")
        return 0

    try:
        plan = plan_narrations(
            pilot_dir / "state.json", pilot_dir / "predictions.jsonl", str(data_path), out_path,
            max_records=max_records, history_hours=float(cfg["history_hours"]),
            llm_enabled=use_llm, force=args.force,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        print("Run scripts/pilot_run.py first, and check --pilot-dir and --data.")
        return 1

    print(f"{len(plan.candidates)} record(s) to narrate; {plan.skipped_existing} already done.")
    if plan.skipped_lines:
        print(f"Warning: skipped {plan.skipped_lines} unreadable line(s) in predictions.jsonl.")

    if args.dry_run:
        for facts in plan.candidates:
            print("=" * 72)
            print(situation_report(facts))
            print("-" * 72)
            print("SYSTEM:", SYSTEM_PROMPT)
            print("PROMPT:", build_prompt(situation_report(facts)))
        return 0

    if use_llm:
        try:
            client.check_model()
        except LlmError as exc:
            print(f"ERROR: {exc}")
            print("Nothing was written. Start Ollama and pull the model, then re-run.")
            return 2

    try:
        counts = run_plan(plan, out_path, client, retries)
    except LlmError as exc:
        print(f"STOPPED: {exc}")
        print("Records finished before the error are kept; re-run to continue.")
        return 2

    print(f"Wrote {counts['llm']} validated SmolLM narration(s) and "
          f"{counts['template']} template narration(s) to {out_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
