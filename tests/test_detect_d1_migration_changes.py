import json
import subprocess

import pytest

from scripts.cloudflare.detect_d1_migration_changes import (
    detect_d1_migration_changes,
)


BASELINE_SHA = "a" * 40
CURRENT_SHA = "b" * 40
REPOSITORY = "rwillers/ordinarium"


class CommandRunner:
    def __init__(self, returncodes=None, run_payload=None):
        self.returncodes = returncodes or {}
        self.run_payload = (
            [{"headSha": BASELINE_SHA}] if run_payload is None else run_payload
        )
        self.commands = []

    def __call__(self, command, **_kwargs):
        self.commands.append(command)
        if command[:3] == ["gh", "run", "list"]:
            return subprocess.CompletedProcess(
                command,
                self.returncodes.get("lookup", 0),
                stdout=json.dumps(self.run_payload),
                stderr="",
            )

        operation = command[1]
        return subprocess.CompletedProcess(
            command,
            self.returncodes.get(operation, 0),
            stdout="",
            stderr="",
        )


def test_code_only_push_detects_migration_since_last_successful_staging_run():
    runner = CommandRunner(returncodes={"diff": 1})

    decision = detect_d1_migration_changes(
        "push", CURRENT_SHA, REPOSITORY, runner=runner
    )

    assert decision.required is True
    assert decision.baseline_sha == BASELINE_SHA
    lookup = runner.commands[0]
    assert lookup[lookup.index("--status") + 1] == "success"
    assert lookup[lookup.index("--workflow") + 1] == "deploy-cloudflare-staging.yml"
    assert runner.commands[-1] == [
        "git",
        "diff",
        "--quiet",
        BASELINE_SHA,
        CURRENT_SHA,
        "--",
        "migrations/d1",
    ]


def test_code_only_push_skips_migrations_after_successful_baseline():
    runner = CommandRunner()

    decision = detect_d1_migration_changes(
        "push", CURRENT_SHA, REPOSITORY, runner=runner
    )

    assert decision.required is False
    assert "last successful staging deployment" in decision.reason


def test_workflow_dispatch_always_requires_migrations_without_lookup():
    runner = CommandRunner()

    decision = detect_d1_migration_changes(
        "workflow_dispatch", CURRENT_SHA, REPOSITORY, runner=runner
    )

    assert decision.required is True
    assert runner.commands == []


@pytest.mark.parametrize(
    ("returncodes", "run_payload"),
    [
        ({"lookup": 1}, None),
        ({}, []),
        ({}, [{"headSha": "not-a-sha"}]),
        ({"fetch": 1}, None),
        ({"merge-base": 1}, None),
        ({"diff": 128}, None),
    ],
)
def test_detection_failures_require_migrations(returncodes, run_payload):
    runner = CommandRunner(returncodes=returncodes, run_payload=run_payload)

    decision = detect_d1_migration_changes(
        "push", CURRENT_SHA, REPOSITORY, runner=runner
    )

    assert decision.required is True
