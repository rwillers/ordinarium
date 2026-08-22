from __future__ import annotations

import subprocess

from scripts.cloudflare.retry_d1_command import run_with_d1_retry


def completed(returncode: int, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(
        args=["npx", "wrangler"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_retries_recognized_d1_overload_then_preserves_success_output(capsys):
    results = iter(
        [
            completed(
                1,
                stderr="D1 DB is overloaded. Requests queued for too long. [code: 7429]\n",
            ),
            completed(0, stdout='[{"results":[{"ok":1}]}]\n'),
        ]
    )
    calls = []
    delays = []

    result = run_with_d1_retry(
        ["npx", "wrangler"],
        runner=lambda *args, **kwargs: (calls.append((args, kwargs)), next(results))[1],
        sleep=delays.append,
        random_value=lambda: 0.5,
    )

    captured = capsys.readouterr()
    assert result == 0
    assert len(calls) == 2
    assert delays == [5.0]
    assert captured.out == '[{"results":[{"ok":1}]}]\n'
    assert "Recognized transient D1 overload" in captured.err


def test_exhausted_d1_overload_returns_last_exit_code():
    attempts = []
    delays = []

    result = run_with_d1_retry(
        ["npx", "wrangler"],
        runner=lambda *args, **kwargs: (
            attempts.append(1),
            completed(23, stderr="D1 DB is overloaded. Too many requests queued.\n"),
        )[1],
        sleep=delays.append,
        random_value=lambda: 0.5,
    )

    assert result == 23
    assert len(attempts) == 4
    assert delays == [5.0, 15.0, 30.0]


def test_non_overload_failure_is_not_retried():
    attempts = []

    result = run_with_d1_retry(
        ["npx", "wrangler"],
        runner=lambda *args, **kwargs: (
            attempts.append(1),
            completed(7, stderr="Authentication failed\n"),
        )[1],
        sleep=lambda _delay: None,
    )

    assert result == 7
    assert len(attempts) == 1
