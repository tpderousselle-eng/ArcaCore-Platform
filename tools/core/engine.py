from pathlib import Path
import os
import subprocess
import sys
import tempfile

from jinja2 import Environment, FileSystemLoader


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

TEMPLATE_DIR = PROJECT_ROOT / "tools" / "templates"


env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    trim_blocks=False,
    lstrip_blocks=False,
)


def write_text_atomic(output_path: Path, content: str):
    """Replace a text file only after its complete contents reach disk."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, output_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def write_bytes_atomic(output_path: Path, content: bytes):
    """Replace a binary file only after its complete contents reach disk."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, output_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def format_python_file(file_path: Path):
    """
    Format a generated Python file using Black.
    """

    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "black",
                str(file_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    except Exception as e:
        print(f"⚠ Black formatting skipped: {e}")


def render_template(
    template_name: str,
    output_path: Path,
    **context,
):
    """
    Render a Jinja template and write it to disk.
    """

    template = env.get_template(template_name)

    rendered = template.render(**context)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=output_path.suffix,
            delete=False,
        ) as temporary:
            temporary.write(rendered)
            temporary_path = Path(temporary.name)

        if output_path.suffix == ".py":
            format_python_file(temporary_path)
        os.replace(temporary_path, output_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    print(f"✓ Created {output_path}")
