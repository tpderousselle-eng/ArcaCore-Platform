from pathlib import Path
import subprocess
import sys

from jinja2 import Environment, FileSystemLoader


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

TEMPLATE_DIR = PROJECT_ROOT / "tools" / "templates"


env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    trim_blocks=False,
    lstrip_blocks=False,
)


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

    output_path.write_text(
        rendered,
        encoding="utf-8",
    )

    #
    # Automatically format generated Python files.
    #

    if output_path.suffix == ".py":
        format_python_file(output_path)

    print(f"✓ Created {output_path}")