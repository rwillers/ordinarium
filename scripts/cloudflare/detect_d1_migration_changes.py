#!/usr/bin/env python3
"""Decide whether a staging deployment must run D1 migrations."""

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


ROOT = Path(__file__).resolve().parents[2]
STAGING_WORKFLOW = "deploy-cloudflare-staging.yml"
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class MigrationDecision:
    required: bool
    reason: str
    baseline_sha: str | None = None


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def _run(
    command: Sequence[str], runner: CommandRunner
) -> subprocess.CompletedProcess[str]:
    return runner(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _last_successful_staging_sha(
    repository: str, runner: CommandRunner
) -> tuple[str | None, str | None]:
    result = _run(
        [
            "gh",
            "run",
            "list",
            "--repo",
            repository,
            "--workflow",
            STAGING_WORKFLOW,
            "--branch",
            "main",
            "--status",
            "success",
            "--limit",
            "1",
            "--json",
            "headSha",
        ],
        runner,
    )
    if result.returncode != 0:
        return None, "the last successful staging run could not be queried"

    try:
        runs = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None, "the staging run lookup returned invalid JSON"

    if not isinstance(runs, list) or len(runs) != 1:
        return None, "no unique successful staging run was found"

    baseline_sha = runs[0].get("headSha") if isinstance(runs[0], dict) else None
    if not isinstance(baseline_sha, str) or not SHA_PATTERN.fullmatch(baseline_sha):
        return None, "the successful staging run had no trustworthy commit SHA"

    return baseline_sha, None


def detect_d1_migration_changes(
    event_name: str,
    current_sha: str,
    repository: str,
    runner: CommandRunner = subprocess.run,
) -> MigrationDecision:
    if event_name == "workflow_dispatch":
        return MigrationDecision(True, "manual deployments always run D1 migrations")

    if event_name != "push" or not SHA_PATTERN.fullmatch(current_sha):
        return MigrationDecision(True, "the deployment event or commit SHA is untrusted")

    baseline_sha, lookup_error = _last_successful_staging_sha(repository, runner)
    if lookup_error or baseline_sha is None:
        return MigrationDecision(True, lookup_error or "no staging baseline was found")

    fetch = _run(
        ["git", "fetch", "--no-tags", "origin", baseline_sha],
        runner,
    )
    if fetch.returncode != 0:
        return MigrationDecision(
            True,
            "the successful staging revision could not be fetched",
            baseline_sha,
        )

    ancestry = _run(
        ["git", "merge-base", "--is-ancestor", baseline_sha, current_sha],
        runner,
    )
    if ancestry.returncode != 0:
        return MigrationDecision(
            True,
            "the successful staging revision is not a verified ancestor",
            baseline_sha,
        )

    diff = _run(
        [
            "git",
            "diff",
            "--quiet",
            baseline_sha,
            current_sha,
            "--",
            "migrations/d1",
        ],
        runner,
    )
    if diff.returncode == 0:
        return MigrationDecision(
            False,
            "no D1 migrations changed since the last successful staging deployment",
            baseline_sha,
        )
    if diff.returncode == 1:
        return MigrationDecision(
            True,
            "D1 migrations changed since the last successful staging deployment",
            baseline_sha,
        )
    return MigrationDecision(
        True,
        "the D1 migration diff could not be established",
        baseline_sha,
    )


def _write_github_output(path: Path, decision: MigrationDecision) -> None:
    with path.open("a", encoding="utf-8") as output:
        output.write(f"required={'true' if decision.required else 'false'}\n")
        if decision.baseline_sha:
            output.write(f"baseline_sha={decision.baseline_sha}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-name", default=os.environ.get("GITHUB_EVENT_NAME", ""))
    parser.add_argument("--current-sha", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument(
        "--repository", default=os.environ.get("GITHUB_REPOSITORY", "")
    )
    parser.add_argument(
        "--github-output",
        type=Path,
        default=Path(os.environ.get("GITHUB_OUTPUT", "")),
    )
    args = parser.parse_args()

    try:
        decision = detect_d1_migration_changes(
            args.event_name,
            args.current_sha,
            args.repository,
        )
    except (OSError, subprocess.SubprocessError) as error:
        decision = MigrationDecision(True, f"migration detection failed: {error}")

    _write_github_output(args.github_output, decision)
    print(f"D1 migrations required: {decision.required} ({decision.reason})")
    if decision.baseline_sha:
        print(f"Last successful staging revision: {decision.baseline_sha}")


if __name__ == "__main__":
    main()
