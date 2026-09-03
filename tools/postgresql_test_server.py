"""Start an isolated PostgreSQL-compatible server for integration tests."""

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import socket
import subprocess
from tempfile import TemporaryDirectory, TemporaryFile
import time


PGLITE_SERVER_ENV = "ARCACORE_PGLITE_SERVER"


@dataclass(frozen=True)
class PostgreSQLTestServer:
    """Connection information for one isolated PostgreSQL test server."""

    url: str
    implementation: str


def _is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def _pglite_executable() -> str | None:
    configured = os.environ.get(PGLITE_SERVER_ENV)
    if configured:
        path = Path(configured).expanduser().resolve()
        if not path.is_file():
            raise RuntimeError(f"{PGLITE_SERVER_ENV} does not name a file: {path}")
        return str(path)
    return shutil.which("pglite-server")


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _wait_for_postgresql(url: str, process: subprocess.Popen | None = None) -> None:
    try:
        import psycopg2
    except ImportError as error:
        raise RuntimeError(
            "Install tools/requirements-postgresql.txt before running the "
            "PostgreSQL integration contract."
        ) from error

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError("The isolated PostgreSQL test server stopped early.")
        try:
            connection = psycopg2.connect(url, connect_timeout=1)
        except psycopg2.OperationalError:
            time.sleep(0.1)
            continue
        connection.close()
        return
    raise RuntimeError("Timed out waiting for the isolated PostgreSQL test server.")


@contextmanager
def _pglite_server(executable: str):
    """Use PostgreSQL compiled to WASM when a restricted root cannot run initdb."""

    port = _free_port()
    url = (
        f"postgresql://postgres:postgres@127.0.0.1:{port}/postgres"
        "?sslmode=disable"
    )
    with TemporaryFile(mode="w+t", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                executable,
                "--db=memory://",
                "--host=127.0.0.1",
                f"--port={port}",
                "--max-connections=20",
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            _wait_for_postgresql(url, process)
            yield PostgreSQLTestServer(url, "PGlite PostgreSQL")
        except Exception as error:
            log.seek(0)
            output = log.read().strip()
            if output:
                error.add_note(f"PGlite server log:\n{output}")
            raise
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


@contextmanager
def postgresql_test_server():
    """Yield a fresh PostgreSQL URL without using the repository backend."""

    try:
        from pgembed import get_server
    except ImportError as error:
        raise RuntimeError(
            "Install tools/requirements-postgresql.txt before running the "
            "PostgreSQL integration contract."
        ) from error

    with TemporaryDirectory(prefix="arcacore-postgresql-") as directory:
        server = None
        startup_error = None
        try:
            server = get_server(
                Path(directory) / "data",
                cleanup_mode="delete",
            )
        except Exception as error:
            startup_error = error

        if server is not None:
            try:
                url = server.get_uri(database="postgres")
                _wait_for_postgresql(url)
                yield PostgreSQLTestServer(url, "pgembed PostgreSQL")
            finally:
                server.cleanup()
            return

        fallback = _pglite_executable() if _is_root() else None
        if fallback is None:
            message = (
                "The embedded PostgreSQL server could not start. Restricted root "
                f"environments may set {PGLITE_SERVER_ENV} to pglite-server."
            )
            raise RuntimeError(message) from startup_error
        with _pglite_server(fallback) as test_server:
            yield test_server
