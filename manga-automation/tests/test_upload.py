"""
Tests for upload_tiktok.py
"""
import json
from unittest.mock import patch, MagicMock, call

import pytest

from scripts.upload_tiktok import (
    get_available_account,
    get_video,
    build_caption,
    record_result,
)


class TestGetAvailableAccount:
    @patch("scripts.upload_tiktok.db.execute_one")
    def test_returns_account_when_available(self, mock_db):
        mock_db.return_value = {"id": 1, "username": "test_account", "cookies_file": None}
        result = get_available_account()
        assert result is not None
        assert result["username"] == "test_account"

    @patch("scripts.upload_tiktok.db.execute_one")
    def test_returns_none_when_no_accounts(self, mock_db):
        mock_db.return_value = None
        result = get_available_account()
        assert result is None


class TestGetVideo:
    @patch("scripts.upload_tiktok.db.execute_one")
    def test_returns_video_when_found(self, mock_db):
        mock_db.return_value = {
            "id": 1,
            "file_path": "/data/videos/test.mp4",
            "caption": "Epic moment!",
            "hashtags": ["manga", "anime"],
            "manga_title": "One Piece",
        }
        result = get_video(1)
        assert result is not None
        assert result["file_path"] == "/data/videos/test.mp4"

    @patch("scripts.upload_tiktok.db.execute_one")
    def test_returns_none_when_not_found(self, mock_db):
        mock_db.return_value = None
        result = get_video(9999)
        assert result is None


class TestBuildCaption:
    def test_includes_caption_and_hashtags(self):
        video = {
            "caption": "This scene broke me",
            "hashtags": ["manga", "anime", "onepice"],
            "manga_title": "One Piece",
        }
        caption = build_caption(video)
        assert "This scene broke me" in caption
        assert "#manga" in caption
        assert "#anime" in caption

    def test_falls_back_to_title_when_no_caption(self):
        video = {
            "caption": None,
            "hashtags": None,
            "manga_title": "Chainsaw Man",
        }
        caption = build_caption(video)
        assert "Chainsaw Man" in caption

    def test_caption_within_tiktok_limit(self):
        video = {
            "caption": "A" * 200,
            "hashtags": ["manga"] * 10,
            "manga_title": "Test",
        }
        caption = build_caption(video)
        assert len(caption) <= 2200


class TestRecordResult:
    @patch("scripts.upload_tiktok.db.execute")
    def test_records_success(self, mock_execute):
        result = {"success": True, "tiktok_url": "https://tiktok.com/video/123", "error": None}
        record_result(video_id=1, account_id=1, result=result)

        # Should call execute multiple times: insert result, update account, update video, insert published
        assert mock_execute.call_count >= 4

    @patch("scripts.upload_tiktok.db.execute")
    def test_records_failure(self, mock_execute):
        result = {"success": False, "tiktok_url": None, "error": "Upload failed"}
        record_result(video_id=1, account_id=1, result=result)

        # Should call execute: insert result, increment failures, update video status
        assert mock_execute.call_count >= 3

    @patch("scripts.upload_tiktok.db.execute")
    def test_increments_failures_on_error(self, mock_execute):
        result = {"success": False, "tiktok_url": None, "error": "Network error"}
        record_result(video_id=2, account_id=3, result=result)

        # Find the call that updates upload_failures
        calls_as_str = [str(c) for c in mock_execute.call_args_list]
        assert any("upload_failures" in s for s in calls_as_str)
