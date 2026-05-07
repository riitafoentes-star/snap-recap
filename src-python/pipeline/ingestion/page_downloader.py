"""
Snap Recap — PageDownloader

Downloads manga pages from MangaDex API or loads them from local paths.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List

import cv2
import httpx
import numpy as np

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from models import PageImage

# MangaDex at-home server endpoint
_MANGADEX_AT_HOME = "https://api.mangadex.org/at-home/server/{chapter_id}"

# Retry configuration
_MAX_RETRIES = 3
_BACKOFF_SECONDS = [1, 2, 4]
_RETRYABLE_STATUS_CODES = {429, 404}


class PageDownloader:
    """Downloads manga pages from MangaDex or loads them from local paths."""

    def download_chapter(self, chapter_id: str) -> List[PageImage]:
        """Download all pages for a MangaDex chapter.

        Calls the MangaDex at-home server API to get page URLs, then downloads
        each page image. Retries up to 3 times with exponential backoff (1s, 2s,
        4s) on HTTP 429 or 404 responses.

        Args:
            chapter_id: MangaDex chapter UUID.

        Returns:
            List of PageImage objects, one per page, in order.

        Raises:
            httpx.HTTPStatusError: If all retries are exhausted.
            httpx.RequestError: On network errors.
        """
        url = _MANGADEX_AT_HOME.format(chapter_id=chapter_id)

        # Fetch at-home server data with retry
        server_data = self._get_with_retry(url)

        base_url = server_data["baseUrl"]
        chapter_data = server_data["chapter"]
        hash_val = chapter_data["hash"]
        page_filenames = chapter_data["data"]  # high-quality pages

        pages: List[PageImage] = []
        for index, filename in enumerate(page_filenames):
            page_url = f"{base_url}/data/{hash_val}/{filename}"
            image_bytes = self._download_bytes_with_retry(page_url)
            arr = np.frombuffer(image_bytes, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError(f"Failed to decode image for page {index} ({filename})")
            pages.append(PageImage(data=img, path=None, index=index))

        return pages

    def from_local(self, paths: List[Path]) -> List[PageImage]:
        """Load manga pages from local file paths.

        Validates each path against path traversal attacks before any filesystem
        access. Reads images as BGR numpy arrays (uint8).

        Args:
            paths: List of Path objects pointing to image files.

        Returns:
            List of PageImage objects with the same length as ``paths``.

        Raises:
            ValueError: If any path contains ``../`` or ``..\\`` (path traversal).
            ValueError: If an image cannot be read.
        """
        # Validate all paths before touching the filesystem
        for path in paths:
            _validate_no_traversal(path)

        pages: List[PageImage] = []
        for index, path in enumerate(paths):
            img = cv2.imread(str(path))
            if img is None:
                raise ValueError(f"Could not read image at path: {path}")
            pages.append(PageImage(data=img, path=path, index=index))

        return pages

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_with_retry(self, url: str) -> dict:
        """GET a JSON endpoint with exponential backoff on retryable errors."""
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = httpx.get(url, timeout=30)
                if response.status_code in _RETRYABLE_STATUS_CODES:
                    if attempt < _MAX_RETRIES - 1:
                        time.sleep(_BACKOFF_SECONDS[attempt])
                        continue
                    response.raise_for_status()
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_BACKOFF_SECONDS[attempt])
        raise last_exc  # type: ignore[misc]

    def _download_bytes_with_retry(self, url: str) -> bytes:
        """Download raw bytes with exponential backoff on retryable errors."""
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = httpx.get(url, timeout=60)
                if response.status_code in _RETRYABLE_STATUS_CODES:
                    if attempt < _MAX_RETRIES - 1:
                        time.sleep(_BACKOFF_SECONDS[attempt])
                        continue
                    response.raise_for_status()
                response.raise_for_status()
                return response.content
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_BACKOFF_SECONDS[attempt])
        raise last_exc  # type: ignore[misc]


def _validate_no_traversal(path: Path) -> None:
    """Raise ValueError if the path string contains traversal sequences.

    Checks the raw string representation of the path for ``../`` or ``..\\``
    without accessing the filesystem.

    Args:
        path: Path to validate.

    Raises:
        ValueError: If the path contains a traversal sequence.
    """
    # Use the raw string as passed — Path() may normalize away trailing slashes,
    # so we also check the parts of the path for ".." components.
    path_str = str(path)

    # Check for literal traversal sequences in the string representation
    if "../" in path_str or "..\\" in path_str:
        raise ValueError(
            f"Path traversal detected in path: {path!r}. "
            "Paths containing '../' or '..\\ ' are not allowed."
        )

    # Also check for ".." as a path component (handles Path("..") after normalization)
    parts = path.parts
    if ".." in parts:
        raise ValueError(
            f"Path traversal detected in path: {path!r}. "
            "Paths containing '..' components are not allowed."
        )
