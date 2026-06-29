from pathlib import Path


def require_generated_file(path: Path) -> Path:
    if not path.exists() or path.stat().st_size == 0:
        raise FileNotFoundError(f"Generated file is missing or empty: {path}")
    return path
