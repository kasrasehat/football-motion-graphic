from match_collector.player_stats import player_snapshot


def test_metrics_join_by_player_id_and_preserve_zero_and_missing_values():
    roster = {
        "teams": [{"id": "h", "name": "Home", "side": "HOME"}],
        "players": [{"participant": {"id": pid, "name": "Smith"}, "teamId": "h"} for pid in ("a", "b")],
    }
    stats = {
        "stats": {
            "entries": [
                {"playerId": "b", "typeId": "SHOTS", "value": "0"},
                {"playerId": "c", "typeId": "SHOTS", "value": "3"},
            ]
        },
        "ratings": [{"participantId": "b", "value": "7.1"}],
    }
    a, b, c = player_snapshot(roster, stats)["players"]
    assert a["metrics"] == {}
    assert b["metrics"]["SHOTS"] == [{"value": "0"}]
    assert b["rating"] == "7.1" and b["team"] == "Home"
    assert c["player_id"] == "c" and "name" not in c
