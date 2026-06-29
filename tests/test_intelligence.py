"""Phase 1/2 — post intelligence + retention engine (pure logic)."""
from tools.intelligence import (
    classify_post_purpose, community_signal, compute_post_intelligence,
    detect_spikes, forward_rate, reaction_density,
)
from tools.retention import build_retention_triggers, fatigue_score, recycle_candidates


def _post(views, reactions=0, forwards=0, fmt="text", text=""):
    return {"views": views, "reactions": reactions, "forwards": forwards, "format": fmt, "text": text}


def test_virality_rates_and_purpose():
    assert forward_rate(_post(100, forwards=5)) == 5.0
    assert reaction_density(_post(100, reactions=8)) == 8.0
    assert classify_post_purpose(_post(100, forwards=5)) == "growth"          # forwarded
    assert classify_post_purpose(_post(100, reactions=6)) == "retention"      # sticky
    assert classify_post_purpose(_post(100, fmt="poll")) == "retention"
    assert classify_post_purpose(_post(100, text="Join now https://t.me/x")) == "conversion"
    assert classify_post_purpose(_post(100, reactions=1)) == "standard"


def test_spikes_and_community_signal():
    posts = [_post(100, reactions=1) for _ in range(4)] + [_post(100, reactions=30)]
    assert 4 in detect_spikes(posts)                                          # the 30-reaction post spikes
    silent = community_signal([_post(1000, reactions=1)])
    assert silent["silent"] is True and silent["state"] == "silent"
    active = community_signal([_post(100, reactions=20, forwards=5)])
    assert active["silent"] is False and active["state"] == "active"


def test_compute_post_intelligence_blob():
    posts = [_post(100, forwards=5), _post(100, reactions=6, fmt="poll"), _post(100, reactions=1)]
    intel = compute_post_intelligence(posts, 1000)
    assert intel["posts_analyzed"] == 3
    assert sum(intel["purpose_mix"].values()) == 3
    assert "community_signal" in intel and "format_engagement" in intel


def test_retention_triggers_by_severity():
    none = build_retention_triggers("none", None, "AI")
    assert [t["kind"] for t in none] == ["weekly"]                            # healthy => habit only
    high = build_retention_triggers("high", None, "AI")
    assert high[0]["kind"] == "reengage" and "re-engagement" in high[0]["topic"].lower()
    assert {"series", "cliffhanger", "challenge", "weekly"} <= {t["kind"] for t in high}


def test_fatigue_and_recycle():
    fat = fatigue_score([{"format": "text", "topic": "a"}, {"format": "text", "topic": "a"},
                         {"format": "text", "topic": "a"}])
    assert fat["score"] > 0.5 and fat["flags"]
    rc = recycle_candidates([_post(100, reactions=20), _post(100, reactions=2), _post(100, reactions=0)])
    assert rc and rc[0]["er"] >= rc[-1]["er"]
