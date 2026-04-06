"""Path utilities — canonical source reference computation."""

from pathlib import Path

from kb.config import RAW_DIR


def make_source_ref(source_path: Path, raw_dir: Path | None = None) -> str:
    """Compute a canonical source reference string for a raw source file.

    Produces paths like 'raw/articles/example.md' regardless of OS.
    Falls back to 'raw/<filename>' if source is outside the raw directory.

    Args:
        source_path: Absolute or relative path to the source file.
        raw_dir: Path to raw directory (uses config default if None).

    Returns:
        Forward-slash relative path starting with 'raw/'.
    """
    raw_dir = raw_dir or RAW_DIR
    source_path = Path(source_path).resolve()
    try:
        return str(source_path.relative_to(raw_dir.resolve().parent)).replace("\\", "/")
    except ValueError:
        return f"raw/{source_path.name}"
