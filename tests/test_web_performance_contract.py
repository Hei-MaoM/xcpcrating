"""Contract tests for the web export's performance-oriented shards."""

from xcpc_rating.export_web import (
    build_leaderboard_assets,
    build_player_search_shards,
    player_shard,
)


def test_leaderboard_assets_page_and_school_shards_preserve_global_tied_ranks():
    board = [
        {"key": "a", "name": "A", "org": "X", "rating": 2000.4, "contests": 4},
        {"key": "b", "name": "B", "org": "Y", "rating": 1999.6, "contests": 3},
        {"key": "c", "name": "C", "org": "X", "rating": 1800.0, "contests": 2},
    ]

    meta, pages, schools = build_leaderboard_assets(board, page_size=2)

    assert meta == {
        "total": 3,
        "pageSize": 2,
        "pageCount": 2,
        "schools": [["X", 2], ["Y", 1]],
    }
    assert [row[5] for row in pages[0]] == [1, 1]
    assert [row[5] for row in pages[1]] == [3]
    assert [row[0] for row in schools["X"]] == ["a", "c"]
    assert [row[5] for row in schools["X"]] == [1, 3]


def test_player_search_shards_index_name_and_school_prefix_without_duplicates():
    records = {
        "alice@北京大学": {
            "key": "alice@北京大学",
            "name": "Alice",
            "org": "北京大学",
            "contests": 5,
        },
        "安宁@安徽大学": {
            "key": "安宁@安徽大学",
            "name": "安宁",
            "org": "安徽大学",
            "contests": 2,
        },
    }

    shards = build_player_search_shards(records)

    assert shards[player_shard("a")] == [["alice@北京大学", "Alice", "北京大学", 5]]
    assert shards[player_shard("北")] == [["alice@北京大学", "Alice", "北京大学", 5]]
    # Name and org both begin with 安; the compact row is written only once.
    row = ["安宁@安徽大学", "安宁", "安徽大学", 2]
    assert shards[player_shard("安")].count(row) == 1
