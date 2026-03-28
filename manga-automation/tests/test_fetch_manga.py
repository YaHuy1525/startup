"""
Tests for fetch_trending_manga.py
"""
import json
from unittest.mock import patch, MagicMock

import pytest

from scripts.fetch_trending_manga import (
    fetch_mangadex_trending,
    fetch_anilist_trending,
    merge_and_score,
    upsert_to_db,
)

FAKE_MANGADEX_RESPONSE = {
    "data": [
        {
            "id": "uuid-1",
            "attributes": {
                "title": {"en": "Test Manga"},
                "status": "ongoing",
                "tags": [
                    {
                        "attributes": {
                            "name": {"en": "Action"},
                            "group": "genre",
                        }
                    }
                ],
            },
            "relationships": [],
        }
    ]
}

FAKE_ANILIST_RESPONSE = {
    "data": {
        "Page": {
            "media": [
                {
                    "id": 101,
                    "title": {"english": "Test Manga", "romaji": "Test Manga"},
                    "genres": ["Action"],
                    "trending": 500,
                    "popularity": 10000,
                }
            ]
        }
    }
}


class TestFetchMangadexTrending:
    @patch("scripts.fetch_trending_manga.requests.get")
    def test_returns_list_on_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = FAKE_MANGADEX_RESPONSE
        mock_get.return_value = mock_resp

        result = fetch_mangadex_trending(limit=1)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["mangadex_id"] == "uuid-1"
        assert result[0]["title"] == "Test Manga"
        assert "tags" in result[0]

    @patch("scripts.fetch_trending_manga.requests.get")
    def test_returns_empty_on_http_error(self, mock_get):
        mock_get.side_effect = Exception("Connection error")
        result = fetch_mangadex_trending(limit=10)
        assert result == []


class TestFetchAnilistTrending:
    @patch("scripts.fetch_trending_manga.requests.post")
    def test_returns_list_on_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = FAKE_ANILIST_RESPONSE
        mock_post.return_value = mock_resp

        result = fetch_anilist_trending(per_page=5)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["title"] == "Test Manga"
        assert result[0]["anilist_id"] == 101

    @patch("scripts.fetch_trending_manga.requests.post")
    def test_returns_empty_on_failure(self, mock_post):
        mock_post.side_effect = Exception("Timeout")
        result = fetch_anilist_trending(per_page=5)
        assert result == []


class TestMergeAndScore:
    def test_combines_both_sources(self):
        mangadex = [
            {"mangadex_id": "u1", "title": "Manga A", "tags": [], "genre": "", "status": "ongoing", "source": "mangadex"},
            {"mangadex_id": "u2", "title": "Manga B", "tags": [], "genre": "", "status": "ongoing", "source": "mangadex"},
        ]
        anilist = [
            {"anilist_id": 10, "title": "Manga A", "tags": [], "genre": "", "trending": 100, "source": "anilist"},
            {"anilist_id": 20, "title": "Manga C", "tags": [], "genre": "", "trending": 50, "source": "anilist"},
        ]
        merged = merge_and_score(mangadex, anilist)

        titles = [m["title"] for m in merged]
        assert "Manga A" in titles
        assert "Manga B" in titles
        assert "Manga C" in titles

    def test_scores_are_sorted_descending(self):
        mangadex = [
            {"mangadex_id": "u1", "title": f"Manga {i}", "tags": [], "genre": "", "status": "ongoing", "source": "mangadex"}
            for i in range(5)
        ]
        merged = merge_and_score(mangadex, [])
        scores = [m["trending_score"] for m in merged]
        assert scores == sorted(scores, reverse=True)

    def test_scores_capped_at_100(self):
        mangadex = [
            {"mangadex_id": "u1", "title": "Top Manga", "tags": [], "genre": "", "status": "ongoing", "source": "mangadex"}
        ]
        merged = merge_and_score(mangadex, [])
        assert all(m["trending_score"] <= 100 for m in merged)


class TestUpsertToDb:
    @patch("scripts.fetch_trending_manga.db.execute")
    def test_returns_count_of_saved(self, mock_execute):
        manga_list = [
            {"title": "Manga A", "mangadex_id": "u1", "anilist_id": None, "genre": "", "tags": [], "trending_score": 80.0},
            {"title": "Manga B", "mangadex_id": "u2", "anilist_id": None, "genre": "", "tags": [], "trending_score": 60.0},
        ]
        saved = upsert_to_db(manga_list)
        assert saved == 2
        assert mock_execute.call_count == 2

    @patch("scripts.fetch_trending_manga.db.execute")
    def test_skips_failed_upserts(self, mock_execute):
        mock_execute.side_effect = Exception("DB error")
        manga_list = [
            {"title": "Bad Manga", "mangadex_id": None, "anilist_id": None, "genre": "", "tags": [], "trending_score": 50.0},
        ]
        saved = upsert_to_db(manga_list)
        assert saved == 0
