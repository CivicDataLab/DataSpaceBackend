import subprocess
from pathlib import Path
from typing import List, Union


class DVCManager:
    def __init__(self, repo_path: Union[str, Path]) -> None:
        self.repo_path = Path(repo_path)

    def _run_command(self, command: List[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            command, cwd=str(self.repo_path), capture_output=True, text=True, check=True
        )

    def track_resource(self, file_path: Union[str, Path]) -> str:
        """Add a resource file to DVC tracking"""
        rel_path = Path(file_path).relative_to(self.repo_path)
        self._run_command(["dvc", "add", str(rel_path)])
        return str(rel_path) + ".dvc"

    def commit_version(self, dvc_file: str, message: str) -> None:
        """Commit the DVC file to git"""
        self._run_command(["git", "add", dvc_file])
        self._run_command(["git", "commit", "-m", message])

    def tag_version(self, tag_name: str) -> None:
        """Add a git tag for this version"""
        self._run_command(["git", "tag", tag_name])

    def push_to_remote(self) -> None:
        """Push data to DVC remote and metadata to git"""
        self._run_command(["dvc", "push"])
        self._run_command(["git", "push", "--follow-tags"])
