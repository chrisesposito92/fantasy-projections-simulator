from fantasy_sim.models.game_state import (
    bucket_distance, bucket_score_diff, bucket_yard_zone, bucket_play, GameStateBucket,
)


class TestBucketDistance:
    def test_short(self):
        assert bucket_distance(1) == "short"
        assert bucket_distance(3) == "short"

    def test_medium(self):
        assert bucket_distance(4) == "medium"
        assert bucket_distance(6) == "medium"

    def test_long(self):
        assert bucket_distance(7) == "long"
        assert bucket_distance(10) == "long"

    def test_very_long(self):
        assert bucket_distance(11) == "very_long"
        assert bucket_distance(20) == "very_long"


class TestBucketScoreDiff:
    def test_down_big(self):
        assert bucket_score_diff(-21) == "down_big"
        assert bucket_score_diff(-30) == "down_big"

    def test_down_medium(self):
        assert bucket_score_diff(-14) == "down_med"
        assert bucket_score_diff(-8) == "down_med"

    def test_down_small(self):
        assert bucket_score_diff(-7) == "down_small"
        assert bucket_score_diff(-1) == "down_small"

    def test_tied(self):
        assert bucket_score_diff(0) == "tied"

    def test_up_small(self):
        assert bucket_score_diff(1) == "up_small"
        assert bucket_score_diff(7) == "up_small"

    def test_up_medium(self):
        assert bucket_score_diff(8) == "up_med"
        assert bucket_score_diff(14) == "up_med"

    def test_up_big(self):
        assert bucket_score_diff(15) == "up_big"
        assert bucket_score_diff(35) == "up_big"


class TestBucketYardZone:
    def test_backed_up(self):
        assert bucket_yard_zone(99) == "backed_up"
        assert bucket_yard_zone(80) == "backed_up"

    def test_own_territory(self):
        assert bucket_yard_zone(79) == "own_territory"
        assert bucket_yard_zone(50) == "own_territory"

    def test_opp_territory(self):
        assert bucket_yard_zone(49) == "opp_territory"
        assert bucket_yard_zone(21) == "opp_territory"

    def test_red_zone(self):
        assert bucket_yard_zone(20) == "red_zone"
        assert bucket_yard_zone(1) == "red_zone"


class TestBucketPlay:
    def test_creates_bucket(self):
        bucket = bucket_play(down=1, ydstogo=10, score_differential=0, qtr=1, yardline_100=75)
        assert isinstance(bucket, GameStateBucket)
        assert bucket.down == 1
        assert bucket.distance == "long"
        assert bucket.score_diff == "tied"
        assert bucket.quarter == 1
        assert bucket.yard_zone == "own_territory"

    def test_bucket_is_hashable(self):
        b1 = bucket_play(1, 10, 0, 1, 75)
        b2 = bucket_play(1, 10, 0, 1, 75)
        assert b1 == b2
        assert hash(b1) == hash(b2)
        d = {b1: "test"}
        assert d[b2] == "test"

    def test_different_states_different_buckets(self):
        b1 = bucket_play(1, 10, 0, 1, 75)
        b2 = bucket_play(2, 10, 0, 1, 75)
        assert b1 != b2
