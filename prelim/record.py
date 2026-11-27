"""What every preliminary-design record says about the tree it was made from (Gate C item C14; Gate B
report item 33): the commit, a dirty-tree flag and the list of the dirty files.

The Gate B records of 2026-11-26 carry `git_dirty: true` with one path, the run's own output folder, which
is untracked while the run writes it. Here that folder is left out of the list and named in `excluded`, so
`git_dirty` is true only if something else differs from the commit.
"""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False, cwd=REPO).stdout


def status_path(line):
    """The path of one `git status --porcelain` line (the new path of a rename), without quotes."""
    return line[3:].split(" -> ")[-1].strip().strip('"')


def is_inside(path, folder):
    """True if the repository path is the folder or lies in it."""
    path, folder = path.rstrip("/"), folder.rstrip("/")
    return path == folder or path.startswith(folder + "/")


def dirty_files(lines, own_output=None):
    """The lines of `git status --porcelain` that are not the run's own output folder (repository path)."""
    lines = [ln for ln in lines if ln.strip()]
    if own_output is None:
        return lines
    return [ln for ln in lines if not is_inside(status_path(ln), str(own_output))]


def repo_path(path):
    """A path as text from the repository root, or None if it lies outside the repository."""
    full = Path(path).resolve()
    return str(full.relative_to(REPO)) if full.is_relative_to(REPO) else None


def tree_state(own_output=None):
    """{"commit", "git_dirty", "git_dirty_files", "excluded"} of the whole repository. own_output is the run's
    own record folder as a path from the repository root; it is not counted as a change."""
    # --untracked-files=all lists every new file by itself, not its folder, so only the run's own files are left out
    files = dirty_files(git("status", "--porcelain", "--untracked-files=all").splitlines(), own_output)
    return {"commit": git("rev-parse", "HEAD").strip(), "git_dirty": bool(files), "git_dirty_files": files,
            "excluded": None if own_output is None else str(own_output)}
