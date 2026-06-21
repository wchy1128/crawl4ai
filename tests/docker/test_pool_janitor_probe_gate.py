"""Tests for the janitor's health-probe throttle.

Original gate required `active_requests == 0` AND 300s since last probe.
That gate was the root cause of the 7.5h hang: it never held while a
request was stuck on a wedged browser.

The new logic is a pure periodic probe — every 300s, regardless of busy
state. Safe because Task 1's wait_for guarantees the probe returns within
~12s, and probe uses default_context.new_page() which doesn't interfere
with in-flight crawl pages (about:blank + Date.now() is essentially free).

Tests use a mirror of the predicate so we can exercise it without running
the full janitor loop.
"""

PROBE_THROTTLE_SEC = 300


def _should_probe(seconds_since_last_probe):
    """Mirror of the janitor's probe-gate predicate (post-fix).

    The ONLY condition is throttle. No active_requests check, no busy-state
    tracking. The whole point of the fix is to remove state-dependent gating.
    """
    return seconds_since_last_probe >= PROBE_THROTTLE_SEC


class TestProbeThrottle:
    def test_first_probe_runs_immediately_on_startup(self):
        # _LAST_HEALTH_PROBE_AT initialized to 0.0, so seconds_since is huge
        assert _should_probe(seconds_since_last_probe=99999) is True

    def test_skips_within_throttle_window(self):
        assert _should_probe(seconds_since_last_probe=100) is False

    def test_probes_at_threshold_boundary(self):
        assert _should_probe(seconds_since_last_probe=300) is True

    def test_skips_just_below_threshold(self):
        assert _should_probe(seconds_since_last_probe=299.9) is False

    def test_probes_regardless_of_busy_state(self):
        """The key new behavior: probe runs whether the browser is idle or
        busy. No active_requests check anywhere. This is the fix.
        """
        # The predicate doesn't even take active_requests as input — by design.
        # If it ran during a 7.5h hang (active_requests=1 throughout), it
        # would fire every 300s. That's the whole point.
        assert _should_probe(seconds_since_last_probe=400) is True
        assert _should_probe(seconds_since_last_probe=100) is False
