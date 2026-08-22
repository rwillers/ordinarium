"""Run an idempotent Wrangler D1 command with bounded overload retries."""

from __future__ import annotations

import argparse
import random
import subprocess
import sys
import time
from collections.abc import Callable, Sequence


D1_OVERLOAD_MARKERS = (
    "D1 DB is overloaded. Requests queued for too long.",
    "D1 DB is overloaded. Too many requests queued.",
    "[code: 7429]",
)
RETRY_DELAYS_SECONDS = (5.0, 15.0, 30.0)


def run_with_d1_retry(
    command: Sequence[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
    random_value: Callable[[], float] = random.random,
) -> int:
    """Return the command exit code, retrying only recognized D1 overloads."""

    for attempt in range(len(RETRY_DELAYS_SECONDS) + 1):
        result = runner(command, capture_output=True, text=True, check=False)
        combined_output = f"{result.stdout or ''}\n{result.stderr or ''}"
        if result.returncode == 0:
            _write_output(result, failed=False)
            return 0

        _write_output(result, failed=True)
        delay = RETRY_DELAYS_SECONDS[attempt] if attempt < len(RETRY_DELAYS_SECONDS) else None
        if delay is None or not _is_d1_overload(combined_output):
            return result.returncode

        jittered_delay = delay * (
            0.75 + min(1.0, max(0.0, random_value())) * 0.5
        )
        print(
            "Recognized transient D1 overload; "
            f"retrying attempt {attempt + 2} of {len(RETRY_DELAYS_SECONDS) + 1} "
            f"in {jittered_delay:.1f}s.",
            file=sys.stderr,
        )
        sleep(jittered_delay)

    raise AssertionError("bounded retry loop did not return")


def _is_d1_overload(output: str) -> bool:
    return any(marker in output for marker in D1_OVERLOAD_MARKERS)


def _write_output(
    result: subprocess.CompletedProcess[str],
    *,
    failed: bool,
) -> None:
    if failed:
        if result.stdout:
            sys.stderr.write(result.stdout)
        if result.stderr:
            sys.stderr.write(result.stderr)
        return
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs=argparse.REMAINDER)
    arguments = parser.parse_args()
    command = arguments.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("a command is required after --")
    return run_with_d1_retry(command)


if __name__ == "__main__":
    raise SystemExit(main())
