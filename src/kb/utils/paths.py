"""Path utilities — canonical source reference computation."""

from pathlib import Path

from kb.config import RAW_DIR


def make_source_ref(source_path: Path, raw_dir: Path | None = None) -> str:
    """Compute a canonical source reference string for a raw source file.

    Produces paths like 'raw/articles/example.md' regardless of OS.

    Args:
        source_path: Absolute or relative path to the source file.
        raw_dir: Path to raw directory (uses config default if None).

    Returns:
        Forward-slash relative path starting with 'raw/'.

    Raises:
        ValueError: If source_path is outside the raw directory.
    """
    raw_dir = raw_dir or RAW_DIR
    source_path = Path(source_path).resolve()
    resolved_raw = raw_dir.resolve()
    try:
        rel = source_path.relative_to(resolved_raw)
        return f"{resolved_raw.name}/{rel}".replace("\\", "/")
    except ValueError:
        raise ValueError(
            f"Source path is outside raw directory: {source_path} (raw dir: {raw_dir})"
        )
