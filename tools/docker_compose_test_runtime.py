"""Run an isolated generated application through Docker Compose."""

from dataclasses import dataclass
from http.client import RemoteDisconnected
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DOCKER_RUNTIME_ENV = "ARCACORE_RUN_DOCKER_TESTS"


def docker_runtime_requested() -> bool:
    """Return whether the caller explicitly requested the container contract."""

    return os.environ.get(DOCKER_RUNTIME_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def docker_capability() -> tuple[bool, str]:
    """Check for both the Docker daemon and the Compose v2 plugin."""

    if shutil.which("docker") is None:
        return False, "the docker executable is not available"
    checks = (
        (["docker", "version", "--format", "{{.Server.Version}}"], "Docker daemon"),
        (["docker", "compose", "version"], "Docker Compose v2"),
    )
    for command, label in checks:
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                check=False,
                text=True,
                timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return False, f"{label} check failed: {error}"
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            return False, f"{label} is unavailable: {detail or 'unknown error'}"
    return True, "Docker daemon and Compose v2 are available"


class DockerCommandError(RuntimeError):
    """A Compose command failed without exposing fixture secrets."""


@dataclass
class DockerComposeTestRuntime:
    """Small, secret-aware driver for one generated Compose project."""

    root: Path
    project_name: str
    api_port: int
    secrets: tuple[str, ...] = ()

    @property
    def compose_prefix(self) -> list[str]:
        return [
            "docker",
            "compose",
            "--project-name",
            self.project_name,
            "--project-directory",
            str(self.root),
            "--file",
            str(self.root / "docker-compose.yml"),
            "--env-file",
            str(self.root / ".env"),
        ]

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.api_port}"

    def _redact(self, value: str) -> str:
        redacted = value
        for secret in self.secrets:
            if secret:
                redacted = redacted.replace(secret, "<redacted>")
        return redacted

    def run(self, arguments: list[str], timeout: int = 180) -> str:
        command = [*self.compose_prefix, *arguments]
        try:
            completed = subprocess.run(
                command,
                cwd=self.root,
                capture_output=True,
                check=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise DockerCommandError(
                f"Docker Compose command could not complete: {arguments[0]}: {error}"
            ) from error
        if completed.returncode != 0:
            output = "\n".join(
                part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
            )
            raise DockerCommandError(
                self._redact(
                    f"Docker Compose command failed: {' '.join(arguments)}\n{output}"
                )
            )
        return completed.stdout.strip()

    def validate_configuration(self) -> None:
        self.run(["config", "--quiet"], timeout=30)

    def build(self) -> None:
        self.run(["build", "api"], timeout=600)

    def start(self) -> None:
        self.run(["up", "--detach"], timeout=300)

    def restart_api(self) -> None:
        self.run(["restart", "api"], timeout=120)

    def stop_preserving_storage(self) -> None:
        self.run(["down", "--remove-orphans", "--timeout", "10"], timeout=120)

    def clean(self) -> None:
        self.run(
            ["down", "--volumes", "--remove-orphans", "--rmi", "local", "--timeout", "10"],
            timeout=180,
        )

    def wait_until_healthy(self, timeout: int = 180) -> dict:
        deadline = time.monotonic() + timeout
        last_error = "the API did not respond"
        while time.monotonic() < deadline:
            try:
                body = self.request_json("GET", "/health", timeout=3)
                if body == {"status": "ok", "database": "connected"}:
                    return body
                last_error = f"unexpected health response: {body!r}"
            except (
                RuntimeError,
                URLError,
                TimeoutError,
                ValueError,
                RemoteDisconnected,
            ) as error:
                last_error = str(error)
            time.sleep(1)
        raise RuntimeError(f"Timed out waiting for generated API health: {last_error}")

    def request_json(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 20,
    ) -> dict | list:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request_headers = {"Accept": "application/json", **(headers or {})}
        if data is not None:
            request_headers["Content-Type"] = "application/json"
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers=request_headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"{method} {path} returned HTTP {error.code}: {body}"
            ) from error
        if not raw:
            return {}
        return json.loads(raw)

    def database_probe(self) -> str:
        return self.run(
            [
                "exec",
                "-T",
                "postgres",
                "psql",
                "--username",
                "arcacore",
                "--dbname",
                "arcacore",
                "--tuples-only",
                "--no-align",
                "--command",
                "SELECT 1",
            ],
            timeout=30,
        ).strip()

    def running_services(self) -> set[str]:
        output = self.run(["ps", "--status", "running", "--services"], timeout=30)
        return set(output.splitlines())

    def api_image_id(self) -> str:
        return self.run(["images", "--quiet", "api"], timeout=30).strip()

    def image_history(self, image_id: str) -> str:
        try:
            completed = subprocess.run(
                ["docker", "history", "--no-trunc", image_id],
                cwd=self.root,
                capture_output=True,
                check=False,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise DockerCommandError(f"Docker image history check failed: {error}") from error
        if completed.returncode != 0:
            raise DockerCommandError(
                self._redact(
                    "Docker image history check failed:\n"
                    + (completed.stderr or completed.stdout).strip()
                )
            )
        return completed.stdout
