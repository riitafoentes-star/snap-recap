"""
Tests for StateManager — Task 3.

Covers:
- save/load round-trip (unit tests)
- load returns None for missing checkpoint
- credentials are stripped from checkpoints
- Property 1: checkpoint round-trip with arbitrary serializable data (hypothesis)

**Validates: Requirements 2.1, 2.2, 2.3, 2.5, 14.1**
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# Ensure src-python is on the path.
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import JobStatus
from state_manager import (
    StateManager,
    _SENSITIVE_ENV_NAMES,
    _collect_sensitive_values,
    _strip_credentials,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manager(tmp_path: Path) -> StateManager:
    return StateManager(tmp_path / "output")


# ---------------------------------------------------------------------------
# Unit tests — save / load round-trip
# ---------------------------------------------------------------------------


class TestSaveLoadRoundTrip:
    def test_simple_dict_round_trips(self, tmp_path):
        sm = _make_manager(tmp_path)
        data = {"panels": [1, 2, 3], "config": {"fps": 30}}
        sm.save_checkpoint("job-001", "ingestion", data)
        loaded = sm.load_checkpoint("job-001", "ingestion")
        assert loaded == data

    def test_list_round_trips(self, tmp_path):
        sm = _make_manager(tmp_path)
        data = [10, 20, 30, "hello"]
        sm.save_checkpoint("job-002", "intelligence", data)
        loaded = sm.load_checkpoint("job-002", "intelligence")
        assert loaded == data

    def test_nested_structure_round_trips(self, tmp_path):
        sm = _make_manager(tmp_path)
        data = {"a": {"b": {"c": [1, 2, {"d": True}]}}}
        sm.save_checkpoint("job-003", "production", data)
        loaded = sm.load_checkpoint("job-003", "production")
        assert loaded == data

    def test_none_value_round_trips(self, tmp_path):
        sm = _make_manager(tmp_path)
        sm.save_checkpoint("job-004", "ingestion", None)
        loaded = sm.load_checkpoint("job-004", "ingestion")
        assert loaded is None

    def test_integer_round_trips(self, tmp_path):
        sm = _make_manager(tmp_path)
        sm.save_checkpoint("job-005", "ingestion", 42)
        loaded = sm.load_checkpoint("job-005", "ingestion")
        assert loaded == 42

    def test_string_round_trips(self, tmp_path):
        sm = _make_manager(tmp_path)
        sm.save_checkpoint("job-006", "ingestion", "hello world")
        loaded = sm.load_checkpoint("job-006", "ingestion")
        assert loaded == "hello world"

    def test_multiple_phases_independent(self, tmp_path):
        sm = _make_manager(tmp_path)
        sm.save_checkpoint("job-007", "ingestion", {"phase": "ingestion"})
        sm.save_checkpoint("job-007", "intelligence", {"phase": "intelligence"})
        assert sm.load_checkpoint("job-007", "ingestion") == {"phase": "ingestion"}
        assert sm.load_checkpoint("job-007", "intelligence") == {"phase": "intelligence"}

    def test_overwrite_checkpoint(self, tmp_path):
        sm = _make_manager(tmp_path)
        sm.save_checkpoint("job-008", "ingestion", {"v": 1})
        sm.save_checkpoint("job-008", "ingestion", {"v": 2})
        loaded = sm.load_checkpoint("job-008", "ingestion")
        assert loaded == {"v": 2}

    def test_creates_output_dir_if_missing(self, tmp_path):
        output_dir = tmp_path / "deep" / "nested" / "output"
        sm = StateManager(output_dir)
        assert output_dir.exists()

    def test_checkpoint_file_exists_after_save(self, tmp_path):
        sm = _make_manager(tmp_path)
        sm.save_checkpoint("job-009", "ingestion", {"x": 1})
        cp = sm.output_dir / "job-009" / "ingestion.checkpoint"
        assert cp.exists()


# ---------------------------------------------------------------------------
# Unit tests — load returns None for missing checkpoint
# ---------------------------------------------------------------------------


class TestLoadMissingCheckpoint:
    def test_returns_none_for_missing_phase(self, tmp_path):
        sm = _make_manager(tmp_path)
        result = sm.load_checkpoint("nonexistent-job", "ingestion")
        assert result is None

    def test_returns_none_for_missing_job(self, tmp_path):
        sm = _make_manager(tmp_path)
        result = sm.load_checkpoint("ghost-job", "production")
        assert result is None

    def test_does_not_raise_file_not_found(self, tmp_path):
        sm = _make_manager(tmp_path)
        # Must not raise FileNotFoundError
        try:
            sm.load_checkpoint("no-such-job", "no-such-phase")
        except FileNotFoundError:
            pytest.fail("load_checkpoint raised FileNotFoundError")

    def test_returns_none_for_phase_not_yet_saved(self, tmp_path):
        sm = _make_manager(tmp_path)
        sm.save_checkpoint("job-010", "ingestion", {"x": 1})
        # intelligence was never saved
        result = sm.load_checkpoint("job-010", "intelligence")
        assert result is None


# ---------------------------------------------------------------------------
# Unit tests — credentials are stripped from checkpoints
# ---------------------------------------------------------------------------


class TestCredentialStripping:
    def _env_with_keys(self):
        """Return a dict of fake env vars for all sensitive names."""
        return {name: f"fake-secret-{name}" for name in _SENSITIVE_ENV_NAMES}

    def test_api_key_string_is_redacted(self, tmp_path):
        fake_env = self._env_with_keys()
        with patch.dict(os.environ, fake_env, clear=False):
            sm = _make_manager(tmp_path)
            secret = fake_env["GEMINI_API_KEY"]
            sm.save_checkpoint("job-cred-1", "ingestion", {"key": secret})
            loaded = sm.load_checkpoint("job-cred-1", "ingestion")
        assert loaded["key"] == "[REDACTED]"
        assert secret not in str(loaded)

    def test_multiple_keys_all_redacted(self, tmp_path):
        fake_env = self._env_with_keys()
        with patch.dict(os.environ, fake_env, clear=False):
            sm = _make_manager(tmp_path)
            data = {name: fake_env[name] for name in _SENSITIVE_ENV_NAMES}
            sm.save_checkpoint("job-cred-2", "ingestion", data)
            loaded = sm.load_checkpoint("job-cred-2", "ingestion")
        for name in _SENSITIVE_ENV_NAMES:
            assert loaded[name] == "[REDACTED]", f"{name} was not redacted"

    def test_nested_api_key_is_redacted(self, tmp_path):
        fake_env = self._env_with_keys()
        with patch.dict(os.environ, fake_env, clear=False):
            sm = _make_manager(tmp_path)
            secret = fake_env["ELEVENLABS_API_KEY"]
            data = {"config": {"nested": {"api_key": secret}}}
            sm.save_checkpoint("job-cred-3", "ingestion", data)
            loaded = sm.load_checkpoint("job-cred-3", "ingestion")
        assert loaded["config"]["nested"]["api_key"] == "[REDACTED]"

    def test_non_sensitive_strings_are_preserved(self, tmp_path):
        fake_env = self._env_with_keys()
        with patch.dict(os.environ, fake_env, clear=False):
            sm = _make_manager(tmp_path)
            data = {"safe_value": "this is fine", "count": 42}
            sm.save_checkpoint("job-cred-4", "ingestion", data)
            loaded = sm.load_checkpoint("job-cred-4", "ingestion")
        assert loaded["safe_value"] == "this is fine"
        assert loaded["count"] == 42

    def test_api_key_in_list_is_redacted(self, tmp_path):
        fake_env = self._env_with_keys()
        with patch.dict(os.environ, fake_env, clear=False):
            sm = _make_manager(tmp_path)
            secret = fake_env["GROQ_API_KEY"]
            data = ["safe", secret, "also-safe"]
            sm.save_checkpoint("job-cred-5", "ingestion", data)
            loaded = sm.load_checkpoint("job-cred-5", "ingestion")
        assert loaded[1] == "[REDACTED]"
        assert loaded[0] == "safe"
        assert loaded[2] == "also-safe"

    def test_original_data_not_mutated(self, tmp_path):
        fake_env = self._env_with_keys()
        with patch.dict(os.environ, fake_env, clear=False):
            sm = _make_manager(tmp_path)
            secret = fake_env["GEMINI_API_KEY"]
            data = {"key": secret}
            sm.save_checkpoint("job-cred-6", "ingestion", data)
        # Original dict must be unchanged
        assert data["key"] == secret

    def test_no_env_vars_set_data_unchanged(self, tmp_path):
        """When no sensitive env vars are set, data passes through unchanged."""
        clean_env = {name: "" for name in _SENSITIVE_ENV_NAMES}
        with patch.dict(os.environ, clean_env, clear=False):
            sm = _make_manager(tmp_path)
            data = {"panels": [1, 2, 3]}
            sm.save_checkpoint("job-cred-7", "ingestion", data)
            loaded = sm.load_checkpoint("job-cred-7", "ingestion")
        assert loaded == data


# ---------------------------------------------------------------------------
# Unit tests — get_job_status
# ---------------------------------------------------------------------------


class TestGetJobStatus:
    def test_no_checkpoints_returns_failed(self, tmp_path):
        sm = _make_manager(tmp_path)
        assert sm.get_job_status("no-job") == JobStatus.FAILED

    def test_all_three_phases_returns_success(self, tmp_path):
        sm = _make_manager(tmp_path)
        for phase in ("ingestion", "intelligence", "production"):
            sm.save_checkpoint("job-s1", phase, {})
        assert sm.get_job_status("job-s1") == JobStatus.SUCCESS

    def test_one_phase_returns_partial(self, tmp_path):
        sm = _make_manager(tmp_path)
        sm.save_checkpoint("job-p1", "ingestion", {})
        assert sm.get_job_status("job-p1") == JobStatus.PARTIAL

    def test_two_phases_returns_partial(self, tmp_path):
        sm = _make_manager(tmp_path)
        sm.save_checkpoint("job-p2", "ingestion", {})
        sm.save_checkpoint("job-p2", "intelligence", {})
        assert sm.get_job_status("job-p2") == JobStatus.PARTIAL


# ---------------------------------------------------------------------------
# Unit tests — list_jobs
# ---------------------------------------------------------------------------


class TestListJobs:
    def test_empty_output_dir_returns_empty_list(self, tmp_path):
        sm = _make_manager(tmp_path)
        assert sm.list_jobs() == []

    def test_single_job_appears_in_list(self, tmp_path):
        sm = _make_manager(tmp_path)
        sm.save_checkpoint("job-list-1", "ingestion", {})
        jobs = sm.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].job_id == "job-list-1"

    def test_multiple_jobs_all_appear(self, tmp_path):
        sm = _make_manager(tmp_path)
        for jid in ("alpha", "beta", "gamma"):
            sm.save_checkpoint(jid, "ingestion", {})
        job_ids = {j.job_id for j in sm.list_jobs()}
        assert job_ids == {"alpha", "beta", "gamma"}

    def test_job_summary_has_correct_status(self, tmp_path):
        sm = _make_manager(tmp_path)
        for phase in ("ingestion", "intelligence", "production"):
            sm.save_checkpoint("complete-job", phase, {})
        jobs = sm.list_jobs()
        assert jobs[0].status == JobStatus.SUCCESS

    def test_job_summary_phases_completed(self, tmp_path):
        sm = _make_manager(tmp_path)
        sm.save_checkpoint("partial-job", "ingestion", {})
        sm.save_checkpoint("partial-job", "intelligence", {})
        jobs = sm.list_jobs()
        assert set(jobs[0].phases_completed) == {"ingestion", "intelligence"}

    def test_created_at_is_iso8601(self, tmp_path):
        sm = _make_manager(tmp_path)
        sm.save_checkpoint("ts-job", "ingestion", {})
        jobs = sm.list_jobs()
        # Should parse without error
        from datetime import datetime
        datetime.fromisoformat(jobs[0].created_at)


# ---------------------------------------------------------------------------
# Property test — Property 1: Checkpoint round-trip
#
# **Validates: Requirements 2.1, 2.2**
#
# For any job_id, phase name, and serializable data object, saving a
# checkpoint and then loading it should produce an object equivalent to
# the original.
# ---------------------------------------------------------------------------

# Strategy for arbitrary serializable data (no numpy arrays, no custom
# classes — just plain Python primitives that pickle handles faithfully).
_serializable = st.recursive(
    st.one_of(
        st.none(),
        st.booleans(),
        st.integers(),
        st.floats(allow_nan=False, allow_infinity=False),
        st.text(max_size=50),
        st.binary(max_size=50),
    ),
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(st.text(max_size=10), children, max_size=5),
        st.tuples(children, children),
    ),
    max_leaves=20,
)

_job_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"),
    min_size=1,
    max_size=20,
)

_phase_strategy = st.sampled_from(["ingestion", "intelligence", "production", "custom"])


@given(job_id=_job_id_strategy, phase=_phase_strategy, data=_serializable)
@settings(max_examples=100)
def test_property_1_checkpoint_round_trip(job_id, phase, data):
    """Property 1: Checkpoint round-trip.

    **Validates: Requirements 2.1, 2.2**

    For any job_id, phase name, and serializable data object, saving a
    checkpoint and then loading it should produce an object equivalent to
    the original (assuming no sensitive env vars are set so data is not
    redacted).
    """
    import tempfile

    # Ensure no sensitive env vars interfere with this property test.
    clean_env = {name: "" for name in _SENSITIVE_ENV_NAMES}
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, clean_env, clear=False):
            sm = StateManager(Path(tmpdir) / "output")
            sm.save_checkpoint(job_id, phase, data)
            loaded = sm.load_checkpoint(job_id, phase)
        assert loaded == data
