#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "click",
#     "requests",
#     "locust",
#     "le-utils",
# ]
# ///
"""
Benchmark Kolibri build variants under load.

Runs the load test against a baseline target plus comparison targets, on this
machine or on a remote device driven by the bench agent. Targets are
name=spec pairs; specs are wheels from PRs (pr:14770), PyPI releases
(release:0.19.4), local files (path/to.whl), worktree builds (worktree:path),
or sweep-style dev editable installs (dev:path, local only).

Examples:
    # Released wheel vs a PR's CI wheel, on a remote device
    python bench.py run --baseline base=release:0.19.4 fix=pr:14770 \
        --suffix r1 --device pi4 --username admin --password admin

    # Dev worktrees locally (sweep.py's old job)
    python bench.py run --baseline base=dev:/path/to/base tpwl=dev:/path/to/tpwl \
        --suffix r1 --username admin --password admin
"""

import json
import os
import subprocess
import sys
import time
import urllib.request

import click
from compare import RUN_CONFIG_FILENAME
from compare import STATS_FILENAME
from executors import LocalExecutor
from executors import RemoteExecutor
from executors import wait_for_server
from hub import Hub
from loadtest import QA_CHANNEL_ID
from loadtest import RESULTS_DIR
from logger import error
from logger import info
from logger import success
from logger import warning
from targets import parse_target
from targets import resolve
from targets import version_from_wheel
from targets import version_tuple
from template import ensure_template

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
LOADTEST = os.path.join(THIS_DIR, "loadtest.py")


def _run_name(target, suffix):
    """The canonical results-dir name for a target's run."""
    return f"{target.name}_{suffix}"


def merge_run_config(results_dir, extra):
    path = os.path.join(results_dir, RUN_CONFIG_FILENAME)
    with open(path) as f:
        config = json.load(f)
    config.update(extra)
    with open(path, "w") as f:
        json.dump(config, f, indent=2)


def warn_if_older(name, target_version, baseline_version):
    if version_tuple(target_version) < version_tuple(baseline_version):
        warning(
            f"Target '{name}' ({target_version}) is older than the baseline "
            f"({baseline_version}); its DB would migrate backwards, which "
            "Kolibri does not support - make the oldest variant the baseline"
        )


def _parse_and_validate(baseline_spec, targets, suffix, device):
    """Parse target specs and validate constraints before doing any real work."""
    baseline = parse_target(baseline_spec)
    comparisons = [parse_target(t) for t in targets]
    all_targets = [baseline] + comparisons

    if device and any(t.is_dev for t in all_targets):
        raise click.ClickException(
            "dev: targets cannot run on a remote device - build a wheel "
            "(worktree:/pr:/release:) instead"
        )

    # Fail fast across all N targets; loadtest.py re-checks authoritatively
    # when each run starts.
    for target in all_targets:
        name = _run_name(target, suffix)
        results_dir = os.path.join(RESULTS_DIR, name)
        if os.path.exists(os.path.join(results_dir, STATS_FILENAME)):
            raise click.ClickException(
                f"Results named '{name}' already exist at "
                f"{results_dir}; use a new suffix"
            )

    return baseline, comparisons, all_targets


def _warn_version_order(baseline, comparisons):
    """Warn if any comparison target is older than the baseline."""
    if not baseline.wheel:
        return
    baseline_version = version_from_wheel(baseline.wheel)
    for target in comparisons:
        if target.wheel:
            warn_if_older(
                target.name, version_from_wheel(target.wheel), baseline_version
            )


def _make_executor(
    device, hub_port, hub_host, port, template_dir, tarball, template_hash
):
    """Start hub if needed and return the appropriate executor."""
    hub = None
    if device:
        hub = Hub(port=hub_port, advertise_host=hub_host)
        hub.start()
        if device not in hub.devices:
            info(f"Waiting for device '{device}' to connect. On the device, run:")
            click.echo("")
            for command in hub.connect_commands():
                click.echo(f"    {command}")
            click.echo("")
            seen = set(hub.devices)
            while device not in hub.devices:
                # Surface registrations under other names, so a hostname
                # mismatch doesn't look like a hang.
                for name in set(hub.devices) - seen:
                    seen.add(name)
                    warning(f"Device '{name}' connected; still waiting for '{device}'")
                time.sleep(1)
        success(f"Device '{device}' connected ({hub.devices[device]['platform']})")
        executor = RemoteExecutor(hub, device, port=port)
        executor.seed_template(tarball, template_hash)
    else:
        executor = LocalExecutor(port=port, template_dir=template_dir)
    return hub, executor


def _run_all_targets(
    executor,
    hub,
    all_targets,
    suffix,
    username,
    password,
    users,
    spawn_rate,
    duration,
    run_extra,
):
    """Run each target in sequence; return list of failed run names."""
    failures = []
    try:
        for index, target in enumerate(all_targets):
            run_name = _run_name(target, suffix)
            info(f"=== {run_name} ===")
            try:
                _run_target(
                    executor,
                    target,
                    run_name,
                    username,
                    password,
                    users,
                    spawn_rate,
                    duration,
                    run_extra,
                )
            except click.ClickException as exc:
                if index == 0:
                    raise click.ClickException(
                        f"Baseline run failed; aborting sweep:\n{exc.message}"
                    )
                error(f"{run_name} failed: {exc.message}")
                failures.append(run_name)
                continue
            success(f"{run_name} complete")
    finally:
        executor.restore()
        if hub:
            hub.stop()
    return failures


@click.group()
def cli():
    """Benchmark Kolibri build variants under load."""


@cli.command()
@click.argument("targets", nargs=-1)
@click.option("--baseline", "baseline_spec", required=True, help="name=spec")
@click.option("--suffix", required=True, help="Run name suffix: <name>_<suffix>")
@click.option("--device", default=None, help="Run servers on this registered device")
@click.option("--port", default=8001, show_default=True, help="Kolibri server port")
@click.option("--hub-host", default=None, help="Hub host to advertise to devices")
@click.option("--hub-port", default=8765, show_default=True)
@click.option("--username", required=True)
@click.option("--password", required=True)
@click.option("--users", default=50, show_default=True)
@click.option("--spawn-rate", default=50, show_default=True)
@click.option("--duration", default="3m", show_default=True)
@click.option("--regenerate-template", is_flag=True)
def run(
    targets,
    baseline_spec,
    suffix,
    device,
    port,
    hub_host,
    hub_port,
    username,
    password,
    users,
    spawn_rate,
    duration,
    regenerate_template,
):
    """Run the load test against the baseline, then each comparison target."""
    baseline, comparisons, all_targets = _parse_and_validate(
        baseline_spec, targets, suffix, device
    )

    for target in all_targets:
        resolve(target)

    _warn_version_order(baseline, comparisons)

    template_dir, tarball, template_hash = ensure_template(
        baseline,
        users,
        QA_CHANNEL_ID,
        username,
        password,
        port,
        regenerate=regenerate_template,
    )

    hub, executor = _make_executor(
        device, hub_port, hub_host, port, template_dir, tarball, template_hash
    )

    run_extra = {
        "device": device or "local",
        "template_hash": template_hash,
    }
    if device:
        run_extra["device_platform"] = hub.devices[device]["platform"]

    failures = _run_all_targets(
        executor,
        hub,
        all_targets,
        suffix,
        username,
        password,
        users,
        spawn_rate,
        duration,
        run_extra,
    )

    if failures:
        raise click.ClickException(f"Failed runs: {', '.join(failures)}")
    success("Sweep complete")


def _run_target(
    executor,
    target,
    run_name,
    username,
    password,
    users,
    spawn_rate,
    duration,
    run_extra,
):
    executor.prepare(target)
    executor.reset_home()
    try:
        executor.start()
        # For remote executors this re-verifies over the network (the agent
        # only checked locally); for local ones it is a cheap double-check.
        wait_for_server(executor.server_url)
        result = subprocess.run(
            [
                sys.executable,
                LOADTEST,
                "--server",
                executor.server_url,
                "--username",
                username,
                "--password",
                password,
                "--users",
                str(users),
                "--spawn-rate",
                str(spawn_rate),
                "--duration",
                duration,
                "--headless",
                "--name",
                run_name,
                "run",
            ]
        )
        if result.returncode != 0:
            raise click.ClickException("loadtest.py run failed")
    finally:
        try:
            executor.stop()
        except click.ClickException as stop_exc:
            # start() may have failed before launching anything; don't let
            # the cleanup failure mask the original error.
            error(f"Cleanup stop failed (continuing): {stop_exc.message}")
    merge_run_config(os.path.join(RESULTS_DIR, run_name), run_extra)


@cli.command()
@click.option("--hub-host", default=None, help="Hub host to advertise to devices")
@click.option("--hub-port", default=8765, show_default=True)
def listen(hub_host, hub_port):
    """Start the hub and wait for devices (initial device setup)."""
    hub = Hub(port=hub_port, advertise_host=hub_host)
    hub.start()
    info("Hub running. On each device, run:")
    click.echo("")
    for command in hub.connect_commands():
        click.echo(f"    {command}")
    click.echo("")
    seen = set()
    try:
        while True:
            for name, device_info in hub.devices.items():
                if name not in seen:
                    seen.add(name)
                    success(
                        f"Device '{name}' connected: {device_info['platform']} "
                        f"(python {device_info['python']}, {device_info['ip']})"
                    )
            time.sleep(1)
    except KeyboardInterrupt:
        hub.stop()


@cli.command()
@click.option("--hub-port", default=8765, show_default=True)
def devices(hub_port):
    """List devices registered with the currently-running hub."""
    try:
        with urllib.request.urlopen(
            f"http://localhost:{hub_port}/devices", timeout=5
        ) as resp:
            registered = json.loads(resp.read())
    except OSError:
        raise click.ClickException(
            f"No hub answering on port {hub_port} - is bench.py run/listen active?"
        )
    if not registered:
        info("No devices registered")
    for name, device_info in registered.items():
        click.echo(
            f"{name}: {device_info['platform']} "
            f"(python {device_info['python']}, {device_info['ip']})"
        )


if __name__ == "__main__":
    cli()
