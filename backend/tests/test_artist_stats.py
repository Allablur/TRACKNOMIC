import uuid

import pytest

from app.services.ingestion import save_artist

pytestmark = pytest.mark.integration


def test_catalogue_stats_deduplicate_ids_and_preserve_partial_dates(client, db):
    shared = {"id": "stats-shared", "title": "Shared", "position": 1, "duration_ms": 180000}
    artist = save_artist(
        db,
        {
            "id": "stats-artist",
            "name": "Statistics fixture",
            "albums": [
                {
                    "id": "stats-album",
                    "title": "Album",
                    "release_type": "album",
                    "release_date": "2020",
                    "tracks": [
                        shared,
                        {"id": "stats-unknown", "title": "Unknown duration", "position": 2},
                    ],
                },
                {
                    "id": "stats-single",
                    "title": "Single",
                    "release_type": "single",
                    "release_date": "2022-03",
                    "tracks": [
                        shared,
                        {
                            "id": "stats-equal-duration",
                            "title": "Different ID",
                            "position": 2,
                            "duration_ms": 180000,
                        },
                    ],
                },
                {
                    "id": "stats-compilation",
                    "title": "Compilation",
                    "release_type": "compilation",
                    "release_date": "2022-04-17",
                },
                {"id": "stats-undated", "title": "Undated"},
                {"id": "stats-invalid", "title": "Invalid", "release_date": "2024-02-30"},
            ],
        },
        "spotify",
    )
    save_artist(
        db,
        {
            "id": "stats-other",
            "name": "Unrelated",
            "albums": [
                {
                    "id": "stats-other-release",
                    "title": "Unrelated",
                    "release_date": "2025",
                    "tracks": [
                        {
                            "id": "stats-other-track",
                            "title": "Unrelated",
                            "position": 1,
                            "duration_ms": 999999,
                        }
                    ],
                }
            ],
        },
        "spotify",
    )
    result = client.get(f"/api/v1/artists/{artist.id}/catalogue-stats")
    assert result.status_code == 200
    data = result.json()
    assert data["release_count"] == 5
    assert [
        data[k]
        for k in ["album_count", "single_ep_count", "compilation_count", "other_release_count"]
    ] == [1, 1, 1, 2]
    assert data["distinct_track_count"] == 3 and data["track_position_count"] == 4
    assert data["known_duration_track_count"] == 2 and data["known_duration_ms"] == 360000
    assert data["average_known_duration_ms"] == 180000
    assert data["undated_release_count"] == 2
    assert data["latest_release"]["title"] == "Compilation"
    assert data["latest_release"]["release_date"] == "2022-04-17"
    assert data["releases_by_year"] == [
        {"year": 2020, "releases": 1},
        {"year": 2021, "releases": 0},
        {"year": 2022, "releases": 2},
    ]
    assert "listeners" not in data and "streams" not in data
    assert data["calculated_at"]


def test_empty_artist_and_missing_artist_stats(client, db):
    artist = save_artist(db, {"id": "stats-empty", "name": "Empty"}, "spotify")
    data = client.get(f"/api/v1/artists/{artist.id}/catalogue-stats").json()
    assert (
        data["release_count"] == data["distinct_track_count"] == data["track_position_count"] == 0
    )
    assert data["known_duration_ms"] is None and data["average_known_duration_ms"] is None
    assert data["latest_release"] is None and data["releases_by_year"] == []
    assert client.get(f"/api/v1/artists/{uuid.uuid4()}/catalogue-stats").status_code == 404


def test_zero_duration_is_available_and_ep_category_is_counted(client, db):
    artist = save_artist(
        db,
        {
            "id": "stats-zero",
            "name": "Zero",
            "albums": [
                {
                    "id": "stats-ep",
                    "title": "EP",
                    "release_type": "EP",
                    "release_date": "2023",
                    "tracks": [
                        {"id": "stats-zero-track", "title": "Zero", "position": 1, "duration_ms": 0}
                    ],
                }
            ],
        },
        "test",
    )
    data = client.get(f"/api/v1/artists/{artist.id}/catalogue-stats").json()
    assert data["single_ep_count"] == 1 and data["other_release_count"] == 0
    assert data["known_duration_ms"] == data["average_known_duration_ms"] == 0
    assert data["known_duration_track_count"] == 1
    assert data["latest_release"]["release_date"] == "2023"
    assert data["latest_release"]["date_precision"] == "year"
