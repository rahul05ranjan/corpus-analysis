"""Keep corpus-derived output out of commit-ready repository paths."""

from __future__ import annotations

from pathlib import Path

# These repository-local destinations are ignored deliberately. Everything
# else under the checkout is commit-ready and is refused before bytes exist.
SAFE_PREFIXES = (
    ("out",),
    ("fixtures",),
    ("experiments", "m3a", "raw"),
    ("experiments", "m3a", "label-capture", "runs"),
    ("experiments", "m3a", "label-capture", "labels-private"),
)


def _declared_safe_prefixes(root: Path) -> tuple[tuple[str, ...], ...]:
    """Safe prefixes whose directory rule is present in this worktree."""
    try:
        rules = {line.strip() for line in (root / ".gitignore").read_text(
            encoding="utf-8").splitlines()}
    except OSError:
        return ()
    return tuple(prefix for prefix in SAFE_PREFIXES
                 if f"{'/'.join(prefix)}/" in rules)


def _containing_repository(path: Path) -> Path | None:
    """Nearest Git worktree containing `path`, without invoking Git."""
    resolved = path.resolve()
    for parent in (resolved, *resolved.parents):
        marker = parent / ".git"
        if marker.is_file() or (marker.is_dir() and (marker / "HEAD").exists()):
            return parent
    return None


def publication_path_problem(path: Path | str,
                             repo_root: Path | str | None = None) -> str:
    """Why `path` is unsafe for private output; empty means it is allowed."""
    path = Path(path)
    root = Path(repo_root).resolve() if repo_root else _containing_repository(path)
    if root is None:
        return ""
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        return ""
    safe = _declared_safe_prefixes(root)
    if any(rel.parts[:len(prefix)] == prefix for prefix in safe):
        return ""
    return f"output path {rel or Path('.')} is inside the repository and not under an ignored output root"


def refuse_publication_path(path: Path | str,
                            repo_root: Path | str | None = None) -> None:
    """Raise before corpus-derived bytes reach a commit-ready path."""
    problem = publication_path_problem(path, repo_root)
    if problem:
        raise ValueError(problem)
