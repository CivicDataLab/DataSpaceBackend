import os
import subprocess
from typing import Any, Optional, cast

import structlog
from django.conf import settings
from django.core.management.base import BaseCommand

logger = structlog.getLogger(__name__)


class Command(BaseCommand):
    help = "Set up DVC repository for dataset versioning"

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            repo_path = settings.DVC_REPO_PATH

            # Create directory if needed
            if not os.path.exists(repo_path):
                os.makedirs(repo_path)
                self.stdout.write(f"Created DVC repository directory at {repo_path}")

            # Initialize Git and DVC if not already done
            if not os.path.exists(os.path.join(repo_path, ".git")):
                subprocess.run(["git", "init"], cwd=repo_path, check=True)
                self.stdout.write("Initialized Git repository")

            if not os.path.exists(os.path.join(repo_path, ".dvc")):
                subprocess.run(["dvc", "init"], cwd=repo_path, check=True)
                self.stdout.write("Initialized DVC repository")

                # Configure chunking for large files
                subprocess.run(
                    ["dvc", "config", "cache.type", "hardlink,symlink"],
                    cwd=repo_path,
                    check=True,
                )
                subprocess.run(
                    ["dvc", "config", "cache.shared", "group"],
                    cwd=repo_path,
                    check=True,
                )

                # Configure cache size limits to prevent excessive disk usage
                subprocess.run(
                    ["dvc", "config", "cache.size_limit", "10G"],
                    cwd=repo_path,
                    check=True,
                )

                self.stdout.write("Configured DVC for large file handling")

            # Set up remote if configured
            if (
                hasattr(settings, "DVC_REMOTE_NAME")
                and hasattr(settings, "DVC_REMOTE_URL")
                and settings.DVC_REMOTE_NAME
                and settings.DVC_REMOTE_URL
            ):
                # Cast to str to satisfy mypy
                remote_name = cast(str, settings.DVC_REMOTE_NAME)
                remote_url = cast(str, settings.DVC_REMOTE_URL)

                subprocess.run(
                    [
                        "dvc",
                        "remote",
                        "add",
                        remote_name,
                        remote_url,
                    ],
                    cwd=repo_path,
                    check=True,
                )

                # Set as default remote
                subprocess.run(
                    ["dvc", "remote", "default", remote_name],
                    cwd=repo_path,
                    check=True,
                )

                self.stdout.write(f"Configured DVC remote: {remote_name}")

            # Set up Git user if not already configured
            try:
                # Check if Git user is configured
                result = subprocess.run(
                    ["git", "config", "user.name"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                )
                if not result.stdout.strip():
                    subprocess.run(
                        ["git", "config", "user.name", "DataEx Bot"],
                        cwd=repo_path,
                        check=True,
                    )
                    subprocess.run(
                        ["git", "config", "user.email", "dataex@example.com"],
                        cwd=repo_path,
                        check=True,
                    )
                    self.stdout.write("Configured Git user for DVC repository")
            except subprocess.CalledProcessError:
                # If checking fails, set the user anyway
                subprocess.run(
                    ["git", "config", "user.name", "DataEx Bot"],
                    cwd=repo_path,
                    check=True,
                )
                subprocess.run(
                    ["git", "config", "user.email", "dataex@example.com"],
                    cwd=repo_path,
                    check=True,
                )
                self.stdout.write("Configured Git user for DVC repository")

            self.stdout.write(self.style.SUCCESS("DVC repository set up successfully"))

        except Exception as e:
            import traceback

            logger.error(
                f"Failed to set up DVC repository: {str(e)}, Traceback: {traceback.format_exc()}"
            )
            self.stdout.write(
                self.style.ERROR(f"Failed to set up DVC repository: {str(e)}")
            )
