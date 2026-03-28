"""
Tests for check_duplicates.py and image_hash.py
"""
import json
import os
import tempfile
import hashlib
from unittest.mock import patch, MagicMock
from PIL import Image

import pytest

from scripts.utils.image_hash import hash_image, check_and_register
from scripts.check_duplicates import main as check_duplicates_main


def create_test_image(path: str, color: tuple = (255, 0, 0)):
    """Create a small solid-colour test image."""
    img = Image.new("RGB", (10, 10), color)
    img.save(path)


class TestHashImage:
    def test_returns_sha256_hex(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            tmp = f.name
        try:
            create_test_image(tmp)
            result = hash_image(tmp)
            assert len(result) == 64
            assert all(c in "0123456789abcdef" for c in result)
        finally:
            os.unlink(tmp)

    def test_different_images_different_hashes(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f1, \
             tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f2:
            p1, p2 = f1.name, f2.name
        try:
            create_test_image(p1, color=(255, 0, 0))
            create_test_image(p2, color=(0, 255, 0))
            assert hash_image(p1) != hash_image(p2)
        finally:
            os.unlink(p1)
            os.unlink(p2)

    def test_same_image_same_hash(self):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            tmp = f.name
        try:
            create_test_image(tmp)
            assert hash_image(tmp) == hash_image(tmp)
        finally:
            os.unlink(tmp)


class TestCheckAndRegister:
    @patch("scripts.utils.image_hash.db.execute")
    @patch("scripts.utils.image_hash.db.execute_one")
    def test_new_panel_is_not_duplicate(self, mock_one, mock_exec):
        mock_one.return_value = None  # not seen before

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            tmp = f.name
        try:
            create_test_image(tmp)
            is_dup, uses = check_and_register(tmp, manga_id=1, chapter_id=1, panel_index=0, max_uses=5)
            assert is_dup is False
            assert uses == 1
        finally:
            os.unlink(tmp)

    @patch("scripts.utils.image_hash.db.execute")
    @patch("scripts.utils.image_hash.db.execute_one")
    def test_panel_used_max_times_is_duplicate(self, mock_one, mock_exec):
        mock_one.return_value = {"times_used": 5}

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            tmp = f.name
        try:
            create_test_image(tmp)
            is_dup, uses = check_and_register(tmp, manga_id=1, chapter_id=1, panel_index=0, max_uses=5)
            assert is_dup is True
            assert uses == 5
        finally:
            os.unlink(tmp)

    @patch("scripts.utils.image_hash.db.execute")
    @patch("scripts.utils.image_hash.db.execute_one")
    def test_panel_below_max_is_not_duplicate(self, mock_one, mock_exec):
        mock_one.return_value = {"times_used": 3}

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            tmp = f.name
        try:
            create_test_image(tmp)
            is_dup, uses = check_and_register(tmp, manga_id=1, chapter_id=1, panel_index=0, max_uses=5)
            assert is_dup is False
            assert uses == 4
        finally:
            os.unlink(tmp)


class TestCheckDuplicatesMain:
    @patch("scripts.check_duplicates.check_and_register")
    @patch("scripts.check_duplicates.db.execute_one")
    def test_returns_unique_and_duplicate_counts(self, mock_db, mock_check):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = []
            for i in range(3):
                p = os.path.join(tmpdir, f"panel_{i}.jpg")
                create_test_image(p, color=(i * 80, 0, 0))
                paths.append(p)

            mock_db.return_value = {
                "id": 1,
                "manga_id": 1,
                "local_paths": json.dumps(paths),
            }

            # First 2 unique, last 1 is duplicate
            mock_check.side_effect = [
                (False, 1),
                (False, 1),
                (True, 5),
            ]

            result = check_duplicates_main(chapter_id=1)

            assert result["unique_count"] == 2
            assert result["duplicate_count"] == 1
            assert result["total"] == 3

    @patch("scripts.check_duplicates.db.execute_one")
    def test_returns_empty_when_chapter_not_found(self, mock_db):
        mock_db.return_value = None
        result = check_duplicates_main(chapter_id=9999)
        assert result == {}
