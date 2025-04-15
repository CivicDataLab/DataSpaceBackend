import subprocess
from pathlib import Path
from typing import List, Union

import structlog

logger = structlog.getLogger(__name__)


class DVCManager:
    def __init__(self, repo_path: Union[str, Path]) -> None:
        self.repo_path = Path(repo_path)

    def _run_command(self, command: List[str]) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                command,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            # Log the error with details
            logger.error(f"Command failed: {' '.join(command)}, Error: {e.stderr}")
            # You can choose to re-raise or handle differently
            raise

    def track_resource(self, file_path: Union[str, Path], chunked: bool = False) -> str:
        """Add a resource file to DVC tracking with optional chunking for large files"""
        rel_path = Path(file_path).relative_to(self.repo_path)
        cmd = ["dvc", "add"]
        if chunked:
            cmd.append("--chunked")  # Enables chunking for large files
        cmd.append(str(rel_path))
        self._run_command(cmd)
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

    def get_version(self) -> str:
        """Get the current version from DVC"""
        result = self._run_command(["dvc", "version"])
        return str(result.stdout.strip())

    def get_remote(self) -> str:
        """Get the current remote from DVC"""
        result = self._run_command(["dvc", "remote", "list"])
        return str(result.stdout.strip())

    def setup_remote(self, remote_name: str, remote_url: str) -> None:
        """Configure a DVC remote for storing data"""
        self._run_command(["dvc", "remote", "add", remote_name, remote_url])
        self._run_command(["dvc", "remote", "default", remote_name])

    def verify_file(self, file_path: Union[str, Path]) -> bool:
        """Verify file integrity using DVC checksums"""
        rel_path = Path(file_path).relative_to(self.repo_path)
        try:
            result = self._run_command(["dvc", "status", str(rel_path)])
            return "up to date" in str(result.stdout)
        except subprocess.CalledProcessError:
            return False

    def rollback_to_version(
        self, file_path: Union[str, Path], version_tag: str
    ) -> None:
        """Roll back a file to a specific version using DVC and Git"""
        rel_path = Path(file_path).relative_to(self.repo_path)
        dvc_file = str(rel_path) + ".dvc"

        # Checkout the specific version of the DVC file
        self._run_command(["git", "checkout", version_tag, "--", dvc_file])

        # Pull the data for that version
        self._run_command(["dvc", "checkout", str(rel_path)])

    def lock_resource(self, file_path: Union[str, Path]) -> None:
        """Lock a resource to prevent concurrent modifications"""
        rel_path = Path(file_path).relative_to(self.repo_path)
        self._run_command(["dvc", "lock", str(rel_path)])

    def unlock_resource(self, file_path: Union[str, Path]) -> None:
        """Unlock a previously locked resource"""
        rel_path = Path(file_path).relative_to(self.repo_path)
        self._run_command(["dvc", "unlock", str(rel_path)])

    def add_metric(self, metric_file: Union[str, Path], metric_name: str) -> None:
        """Add a file as a DVC metric for tracking"""
        rel_path = Path(metric_file).relative_to(self.repo_path)
        self._run_command(
            ["dvc", "metrics", "add", str(rel_path), "--name", metric_name]
        )

    def show_metrics(self) -> str:
        """Show all tracked metrics"""
        result = self._run_command(["dvc", "metrics", "show"])
        return str(result.stdout.strip())

    def gc_cache(self, force: bool = False) -> None:
        """Clean up unused cache to save disk space"""
        cmd = ["dvc", "gc"]
        if force:
            cmd.append("-f")
        self._run_command(cmd)

    def configure(self, section: str, option: str, value: str) -> None:
        """Configure DVC settings"""
        self._run_command(["dvc", "config", f"{section}.{option}", value])

    def has_changes(self, file_path: Union[str, Path]) -> bool:
        """Check if a file has uncommitted changes"""
        rel_path = Path(file_path).relative_to(self.repo_path)
        try:
            result = self._run_command(["dvc", "status", str(rel_path)])
            # If there are changes, the output will contain the file path
            return str(rel_path) in str(result.stdout)
        except subprocess.CalledProcessError:
            # If the command fails, assume there are changes
            return True
