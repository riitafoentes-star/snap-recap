"""
Snap Recap — StateManager.

Handles checkpoint persistence and job status tracking for the pipeline.
Checkpoints are stored as pickle files under:
    {output_dir}/{job_id}/{phase}.checkpoint

Security: API keys and OAuth tokens are stripped from data before
serialization.  The following environment-variable names are treated as
sensitive and their values are redacted wherever they appear as strings
inside the data graph:

    GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY,
    ELEVENLABS_API_KEY, YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET
"""

from __future__ import annotations

import copy
import os
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from models import JobStatus, JobSummary

# ---------------------------------------------------------------------------
# Sensitive keys that must never appear in checkpoint files
# ---------------------------------------------------------------------------

_SENSITIVE_ENV_NAMES: tuple[str, ...] = (
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "ELEVENLABS_API_KEY",
    "YOUTUBE_CLIENT_ID",
    "YOUTUBE_CLIENT_SECRET",
)

# The three canonical pipeline phases used to determine job status.
_PIPELINE_PHASES = ("ingestion", "intelligence", "production")


def _collect_sensitive_values() -> set[str]:
    """Return the set of non-empty env-var values for all sensitive keys."""
    values: set[str] = set()
    for name in _SENSITIVE_ENV_NAMES:
        val = os.environ.get(name, "")
        if val:
            values.add(val)
    return values


def _strip_credentials(obj: Any, sensitive_values: set[str]) -> Any:
    """Recursively walk *obj* and replace any sensitive string with ``'[REDACTED]'``.

    The function operates on a deep copy so the caller's original object is
    never mutated.  Supported container types: dict, list, tuple, set.
    Strings that exactly match a sensitive value are replaced.  All other
    types are returned unchanged.
    """
    if not sensitive_values:
        return obj

    if isinstance(obj, str):
        return "[REDACTED]" if obj in sensitive_values else obj

    if isinstance(obj, dict):
        return {
            _strip_credentials(k, sensitive_values): _strip_credentials(v, sensitive_values)
            for k, v in obj.items()
        }

    if isinstance(obj, list):
        return [_strip_credentials(item, sensitive_values) for item in obj]

    if isinstance(obj, tuple):
        return tuple(_strip_credentials(item, sensitive_values) for item in obj)

    if isinstance(obj, set):
        return {_strip_credentials(item, sensitive_values) for item in obj}

    # For arbitrary objects, attempt to sanitise __dict__ if present.
    if hasattr(obj, "__dict__"):
        # Work on a shallow copy of the object to avoid mutating the original.
        try:
            obj_copy = copy.copy(obj)
            for attr, val in list(vars(obj_copy).items()):
                setattr(obj_copy, attr, _strip_credentials(val, sensitive_values))
            return obj_copy
        except Exception:
            # If copying/attribute-setting fails, return the object as-is
            # (better to keep the object than to crash the pipeline).
            return obj

    return obj


# ---------------------------------------------------------------------------
# StateManager
# ---------------------------------------------------------------------------


class StateManager:
    """Persist and retrieve pipeline checkpoints.

    Args:
        output_dir: Root directory where job subdirectories are created.
                    The directory is created if it does not already exist.
    """

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _checkpoint_path(self, job_id: str, phase: str) -> Path:
        """Return the filesystem path for a checkpoint file."""
        return self.output_dir / job_id / f"{phase}.checkpoint"

    def _job_dir(self, job_id: str) -> Path:
        """Return the directory that holds all checkpoints for *job_id*."""
        return self.output_dir / job_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_checkpoint(self, job_id: str, phase: str, data: Any) -> None:
        """Serialize *data* to ``{output_dir}/{job_id}/{phase}.checkpoint``.

        API keys and OAuth tokens are stripped from *data* before writing.
        The original *data* object is **not** mutated.

        Args:
            job_id: Unique identifier for the pipeline job.
            phase:  Pipeline phase name (e.g. ``"ingestion"``).
            data:   Arbitrary serializable Python object.
        """
        job_dir = self._job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)

        # Deep-copy then sanitise to avoid mutating the caller's data.
        sensitive = _collect_sensitive_values()
        safe_data = _strip_credentials(copy.deepcopy(data), sensitive)

        checkpoint_path = self._checkpoint_path(job_id, phase)
        with checkpoint_path.open("wb") as fh:
            pickle.dump(safe_data, fh, protocol=pickle.HIGHEST_PROTOCOL)

    def load_checkpoint(self, job_id: str, phase: str) -> Optional[Any]:
        """Deserialize and return the checkpoint for *job_id* / *phase*.

        Returns ``None`` if the checkpoint file does not exist.  Never
        raises :class:`FileNotFoundError`.

        Args:
            job_id: Unique identifier for the pipeline job.
            phase:  Pipeline phase name.

        Returns:
            The deserialized object, or ``None``.
        """
        checkpoint_path = self._checkpoint_path(job_id, phase)
        if not checkpoint_path.exists():
            return None
        with checkpoint_path.open("rb") as fh:
            return pickle.load(fh)  # noqa: S301 — trusted local files only

    def get_job_status(self, job_id: str) -> JobStatus:
        """Return the :class:`~models.JobStatus` for *job_id*.

        Status is derived from which phase checkpoints exist:

        * All three phases present → ``SUCCESS``
        * At least one phase present → ``PARTIAL``
        * No phases present → ``FAILED``

        Args:
            job_id: Unique identifier for the pipeline job.

        Returns:
            A :class:`~models.JobStatus` value.
        """
        completed = [
            phase
            for phase in _PIPELINE_PHASES
            if self._checkpoint_path(job_id, phase).exists()
        ]

        if len(completed) == len(_PIPELINE_PHASES):
            return JobStatus.SUCCESS
        if completed:
            return JobStatus.PARTIAL
        return JobStatus.FAILED

    def list_jobs(self) -> List[JobSummary]:
        """Scan *output_dir* for job subdirectories and return summaries.

        Each immediate subdirectory of *output_dir* is treated as a job.
        The ``created_at`` timestamp is derived from the directory's
        ``st_ctime`` (creation time on Windows, metadata-change time on
        POSIX — good enough for display purposes).

        Returns:
            A list of :class:`~models.JobSummary` objects, one per job.
        """
        summaries: List[JobSummary] = []

        if not self.output_dir.exists():
            return summaries

        for entry in sorted(self.output_dir.iterdir()):
            if not entry.is_dir():
                continue

            job_id = entry.name
            phases_completed = [
                phase
                for phase in _PIPELINE_PHASES
                if (entry / f"{phase}.checkpoint").exists()
            ]
            status = self.get_job_status(job_id)

            # Use directory ctime as a proxy for creation time.
            ctime = entry.stat().st_ctime
            created_at = datetime.fromtimestamp(ctime, tz=timezone.utc).isoformat()

            summaries.append(
                JobSummary(
                    job_id=job_id,
                    status=status,
                    phases_completed=phases_completed,
                    created_at=created_at,
                )
            )

        return summaries
