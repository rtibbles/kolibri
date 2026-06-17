#!/usr/bin/env python3
"""
Kolibri bench device agent.

Fetched and started on a device with the one-liner printed by bench.py:

    curl -s http://<host>:8765/agent.py | python3 -

The hub bakes the hub URL and token into the served copy (EMBEDDED_* below), so
no arguments are needed. Run a local copy with `agent.py <hub_url> --token <t>`.

Stdlib only, Python 3.6+: old, low-resource devices are the point. The agent
registers with the hub, long-polls for commands, executes them, and reports
results. It keeps all state under ~/.kolibri_bench/.
"""

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tarfile
import time
import traceback
from urllib import request
from urllib.error import HTTPError
from urllib.error import URLError

BASE = os.path.expanduser(os.path.join("~", ".kolibri_bench"))
VENVS = os.path.join(BASE, "venvs")
TEMPLATE = os.path.join(BASE, "template")
RUN_HOME = os.path.join(BASE, "run_home")
DOWNLOADS = os.path.join(BASE, "downloads")
HASH_FILE = os.path.join(BASE, "template.hash")
SERVER_LOG = os.path.join(BASE, "server.log")
POLL_TIMEOUT = 40  # > hub's 25s hold
RETRY_DELAY = 5

# Overwritten by the hub when it serves this file (the URL from the Host the
# device used to reach the hub, plus the token), so the fetched agent needs no
# launch arguments. Stay None in the on-disk copy for direct local runs.
EMBEDDED_HUB_URL = None
EMBEDDED_TOKEN = None


def log(message):
    print("[agent] {}".format(message), flush=True)  # noqa: T201


def kolibri_bin(venv):
    if os.name == "nt":
        return os.path.join(venv, "Scripts", "kolibri.exe")
    return os.path.join(venv, "bin", "kolibri")


def venv_python(venv):
    if os.name == "nt":
        return os.path.join(venv, "Scripts", "python.exe")
    return os.path.join(venv, "bin", "python")


def download(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with request.urlopen(url, timeout=600) as resp, open(dest, "wb") as f:
        shutil.copyfileobj(resp, f)
    return dest


def tail(path, lines=50):
    if not os.path.exists(path):
        return "(no log at {})".format(path)
    with open(path, "rb") as f:
        return b"\n".join(f.read().splitlines()[-lines:]).decode("utf-8", "replace")


def port_in_use(port):
    try:
        socket.create_connection(("127.0.0.1", int(port)), timeout=2).close()
        return True
    except OSError:
        return False


def run_checked(cmd, what, **kwargs):
    proc = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "{} failed:\n{}".format(what, proc.stdout.decode("utf-8", "replace"))
        )


def prune_subdirs(parent, keep):
    """Remove subdirectories of `parent` except `keep`. Files (e.g.
    DOWNLOADS/template.tar.gz) are left."""
    if not os.path.isdir(parent):
        return
    for name in os.listdir(parent):
        if name == keep:
            continue
        path = os.path.join(parent, name)
        if os.path.isdir(path):
            log("pruning {}".format(path))
            shutil.rmtree(path, ignore_errors=True)


class Agent(object):
    def __init__(self, hub_url, token):
        self.hub_url = hub_url.rstrip("/")
        self.token = token
        self.device = None
        self.server = None
        self._server_log = None

    # --- hub I/O -----------------------------------------------------------

    def _request(self, path, payload=None, timeout=POLL_TIMEOUT):
        data = json.dumps(payload).encode() if payload is not None else None
        req = request.Request(
            self.hub_url + path,
            data=data,
            headers={
                "Content-Type": "application/json",
                "X-Bench-Token": self.token,
            },
        )
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return resp.status, json.loads(body) if body else None

    def register(self):
        _, body = self._request(
            "/register",
            {
                "hostname": socket.gethostname(),
                "platform": platform.platform(),
                "python": platform.python_version(),
                "cpus": os.cpu_count(),
            },
        )
        self.device = body["device"]
        log("registered as '{}'".format(self.device))

    def run_forever(self):
        self.register()
        while True:
            try:
                status, command = self._request("/poll?device={}".format(self.device))
            except HTTPError as e:
                if e.code == 410:  # hub restarted and forgot us
                    log("hub no longer knows us; re-registering")
                    self.register()
                    continue
                log("poll error {}; retrying in {}s".format(e.code, RETRY_DELAY))
                time.sleep(RETRY_DELAY)
                continue
            except (URLError, OSError):
                log("hub unreachable; retrying in {}s".format(RETRY_DELAY))
                time.sleep(RETRY_DELAY)
                continue
            if status != 200 or command is None:
                continue  # long-poll expired with no command
            log("command: {}".format(command["action"]))
            result = self.execute(command)
            result["id"] = command["id"]
            try:
                self._request("/result?device={}".format(self.device), result)
            except (URLError, OSError):
                log("could not report result; hub will time the command out")

    # --- command execution -------------------------------------------------

    def execute(self, command):
        handler = getattr(self, "do_" + command["action"].replace("-", "_"), None)
        if handler is None:
            return {
                "ok": False,
                "detail": "unknown action '{}'".format(command["action"]),
            }
        try:
            return handler(command.get("params") or {})
        except Exception:
            return {"ok": False, "detail": traceback.format_exc()}

    def do_install(self, params):
        sha, url = params["sha"], params["url"]
        venv = os.path.join(VENVS, sha)
        if os.path.exists(kolibri_bin(venv)):
            return {"ok": True, "detail": "venv cached"}
        # Drop earlier runs' venvs/downloads before installing - prior targets
        # have already been run by this point, so a small SD can't ENOSPC here.
        prune_subdirs(VENVS, sha)
        prune_subdirs(DOWNLOADS, sha)
        # pip refuses wheels whose on-disk name is not a valid PEP 427 wheel
        # filename, so keep the original name under a per-sha directory.
        wheel_dir = os.path.join(DOWNLOADS, sha)
        wheel = download(url, os.path.join(wheel_dir, params["filename"]))
        if os.path.exists(venv):
            shutil.rmtree(venv)  # half-created venv from an aborted install
        run_checked([sys.executable, "-m", "venv", venv], "venv creation")
        run_checked(
            [venv_python(venv), "-m", "pip", "install", wheel],
            "pip install",
        )
        shutil.rmtree(wheel_dir)  # ~100MB, no longer needed; devices are small
        return {"ok": True, "detail": "installed"}

    def do_seed_template(self, params):
        wanted = params["hash"]
        if os.path.exists(HASH_FILE):
            with open(HASH_FILE) as f:
                if f.read() == wanted and os.path.isdir(TEMPLATE):
                    return {"ok": True, "detail": "template cached"}
        tarball = download(params["url"], os.path.join(DOWNLOADS, "template.tar.gz"))
        # Extract beside TEMPLATE, swap in only when fully unpacked, so a
        # failed seed can never leave a partial template for reset-home.
        staging = TEMPLATE + ".staging"
        if os.path.exists(staging):
            shutil.rmtree(staging)
        os.makedirs(staging)
        with tarfile.open(tarball, "r:gz") as tar:
            tar.extractall(staging)
        if os.path.exists(HASH_FILE):
            os.remove(HASH_FILE)
        if os.path.exists(TEMPLATE):
            shutil.rmtree(TEMPLATE)
        os.rename(staging, TEMPLATE)
        with open(HASH_FILE, "w") as f:
            f.write(wanted)
        return {"ok": True, "detail": "template seeded"}

    def do_reset_home(self, params):
        if not os.path.isdir(TEMPLATE):
            return {"ok": False, "detail": "no template seeded yet"}
        if os.path.exists(RUN_HOME):
            shutil.rmtree(RUN_HOME)
        # The template is hundreds of MB and this runs before every target;
        # prefer a CoW copy where cp supports it, falling back to a plain
        # copy (Windows, non-GNU cp).
        if os.name != "nt":
            proc = subprocess.run(
                ["cp", "-a", "--reflink=auto", TEMPLATE, RUN_HOME],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            if proc.returncode == 0:
                return {"ok": True, "detail": "home reset"}
            shutil.rmtree(RUN_HOME, ignore_errors=True)  # partial cp output
        shutil.copytree(TEMPLATE, RUN_HOME)
        return {"ok": True, "detail": "home reset"}

    def _close_log(self):
        if self._server_log is not None:
            self._server_log.close()
            self._server_log = None

    def _terminate_server(self, timeout):
        if self.server is not None:
            self.server.terminate()
            try:
                self.server.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.server.kill()
                self.server.wait()
            self.server = None
        self._close_log()

    def do_start(self, params):
        if self.server is not None and self.server.poll() is None:
            return {"ok": False, "detail": "server already running; stop it first"}
        venv = os.path.join(VENVS, params["sha"])
        port = str(params["port"])
        # A foreign process on the port would pass the readiness check below
        # and get load-tested in kolibri's place.
        if port_in_use(port):
            return {
                "ok": False,
                "detail": "port {} is already in use by another process".format(port),
            }
        env = dict(os.environ)
        env["KOLIBRI_HOME"] = RUN_HOME
        # Agents run wheels (production mode); don't let a dev shell's
        # KOLIBRI_RUN_MODE=dev leak in, as LocalExecutor guards against too.
        env.pop("KOLIBRI_RUN_MODE", None)
        self._close_log()
        self._server_log = open(SERVER_LOG, "wb")
        self.server = subprocess.Popen(
            [kolibri_bin(venv), "start", "--foreground", "--port", port],
            env=env,
            stdout=self._server_log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.time() + 300
        url = "http://127.0.0.1:{}/api/public/info/".format(port)
        while time.time() < deadline:
            if self.server.poll() is not None:
                self._close_log()
                return {
                    "ok": False,
                    "detail": "kolibri exited; log tail:\n" + tail(SERVER_LOG),
                }
            try:
                with request.urlopen(url, timeout=5) as resp:
                    info = json.loads(resp.read())
                # Belt and braces: make sure it is OUR kolibri answering.
                if info.get("application") != "kolibri":
                    self._terminate_server(30)
                    return {
                        "ok": False,
                        "detail": "a non-kolibri server is answering on port {}".format(
                            port
                        ),
                    }
                return {
                    "ok": True,
                    "detail": "serving kolibri {} on port {}".format(
                        info.get("kolibri_version"), port
                    ),
                }
            except (URLError, OSError, ValueError):
                time.sleep(2)
        self._terminate_server(30)
        return {
            "ok": False,
            "detail": "server did not come up; log tail:\n" + tail(SERVER_LOG),
        }

    def do_stop(self, params):
        if self.server is None or self.server.poll() is not None:
            self._close_log()
            self.server = None
            return {"ok": True, "detail": "no server running"}
        self._terminate_server(60)
        return {"ok": True, "detail": "stopped"}

    def do_status(self, params):
        running = self.server is not None and self.server.poll() is None
        return {
            "ok": True,
            "detail": json.dumps(
                {"server_running": running, "platform": platform.platform()}
            ),
        }


def main():
    parser = argparse.ArgumentParser(description="Kolibri bench device agent")
    parser.add_argument("hub_url", nargs="?", default=EMBEDDED_HUB_URL)
    parser.add_argument("--token", default=EMBEDDED_TOKEN)
    args = parser.parse_args()
    if not args.hub_url or not args.token:
        parser.error("hub_url and --token are required")
    for directory in (BASE, VENVS, DOWNLOADS):
        os.makedirs(directory, exist_ok=True)
    agent = Agent(args.hub_url, args.token)
    while True:
        try:
            agent.run_forever()
        except (URLError, OSError):
            log("lost hub; retrying in {}s".format(RETRY_DELAY))
            time.sleep(RETRY_DELAY)


if __name__ == "__main__":
    main()
