import traceback

from hibiki_logger.throttle import DiscordThrottle, signature


def make_trace(exc_type=ValueError, message="boom", line_marker="f"):
    """Produce a real traceback string raised from a named function."""

    def raiser():
        raise exc_type(message)

    raiser.__name__ = line_marker
    try:
        raiser()
    except Exception as e:  # noqa: BLE001 - the traceback is the point
        return "".join(traceback.format_exception(type(e), e, e.__traceback__))


class FakeClock:
    """Monotonic clock under test control."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class TestSignature:
    def test_varying_messages_share_a_signature(self):
        """The case message-keyed dedup gets wrong.

        Messages routinely embed ids, so a single repeating fault would
        otherwise present as an unbounded number of distinct alerts.
        """
        signatures = set()
        for order_id in range(5):
            try:
                raise ValueError(f"failed to process order {order_id}")
            except ValueError as e:
                trace = "".join(
                    traceback.format_exception(type(e), e, e.__traceback__)
                )
                signatures.add(
                    signature("ERROR", str(e), "app.orders", trace)
                )
        assert len(signatures) == 1

    def test_different_exception_types_differ(self):
        a = signature("ERROR", "x", "app.x", make_trace(ValueError))
        b = signature("ERROR", "x", "app.x", make_trace(KeyError))
        assert a != b

    def test_different_loggers_differ(self):
        trace = make_trace()
        assert signature("ERROR", "x", "app.a", trace) != signature(
            "ERROR", "x", "app.b", trace
        )

    def test_falls_back_to_message_without_trace(self):
        assert signature("ERROR", "one", "app.x") != signature(
            "ERROR", "two", "app.x"
        )
        assert signature("ERROR", "one", "app.x") == signature(
            "ERROR", "one", "app.x"
        )

    def test_handles_unparseable_trace(self):
        """A trace with no recognisable frames must not raise."""
        assert signature("ERROR", "msg", "app.x", "not really a traceback")


class TestDeduplication:
    def test_burst_of_identical_errors_sends_once(self):
        clock = FakeClock()
        throttle = DiscordThrottle(
            dedup_window=300, max_per_minute=1000, clock=clock
        )
        trace = make_trace()

        sends = 0
        for _ in range(500):
            clock.advance(0.01)
            if throttle.check("ERROR", "boom", "app.x", trace).send:
                sends += 1

        assert sends == 1

    def test_suppressed_count_surfaces_after_window(self):
        clock = FakeClock()
        throttle = DiscordThrottle(
            dedup_window=300, max_per_minute=1000, clock=clock
        )
        trace = make_trace()

        for _ in range(500):
            clock.advance(0.01)
            throttle.check("ERROR", "boom", "app.x", trace)

        clock.advance(301)
        decision = throttle.check("ERROR", "boom", "app.x", trace)
        assert decision.send is True
        assert decision.suppressed == 499

    def test_count_resets_after_being_reported(self):
        clock = FakeClock()
        throttle = DiscordThrottle(dedup_window=10, max_per_minute=1000, clock=clock)
        trace = make_trace()

        throttle.check("ERROR", "boom", "app.x", trace)
        throttle.check("ERROR", "boom", "app.x", trace)
        clock.advance(11)
        assert throttle.check("ERROR", "boom", "app.x", trace).suppressed == 1
        clock.advance(11)
        assert throttle.check("ERROR", "boom", "app.x", trace).suppressed == 0

    def test_distinct_faults_are_not_collapsed(self):
        clock = FakeClock()
        throttle = DiscordThrottle(dedup_window=300, max_per_minute=1000, clock=clock)
        assert throttle.check("ERROR", "a", "app.x", make_trace(ValueError)).send
        assert throttle.check("ERROR", "b", "app.x", make_trace(KeyError)).send


class TestSendBudget:
    def test_budget_caps_distinct_alerts(self):
        clock = FakeClock()
        throttle = DiscordThrottle(dedup_window=300, max_per_minute=5, clock=clock)

        sends = 0
        for i in range(500):
            clock.advance(0.01)
            if throttle.check("ERROR", f"msg {i}", "app.x").send:
                sends += 1

        assert sends == 5

    def test_dropped_count_surfaces_on_next_send(self):
        clock = FakeClock()
        throttle = DiscordThrottle(dedup_window=300, max_per_minute=5, clock=clock)

        for i in range(500):
            clock.advance(0.01)
            throttle.check("ERROR", f"msg {i}", "app.x")

        clock.advance(61)
        decision = throttle.check("ERROR", "fresh", "app.x")
        assert decision.send is True
        assert decision.dropped == 495

    def test_budget_recovers_as_window_slides(self):
        clock = FakeClock()
        throttle = DiscordThrottle(dedup_window=1, max_per_minute=2, clock=clock)

        assert throttle.check("ERROR", "a", "app.x").send
        assert throttle.check("ERROR", "b", "app.x").send
        assert not throttle.check("ERROR", "c", "app.x").send

        clock.advance(61)
        assert throttle.check("ERROR", "d", "app.x").send

    def test_dedup_runs_before_budget(self):
        """Repeats of an already-sent fault must not consume budget."""
        clock = FakeClock()
        throttle = DiscordThrottle(dedup_window=300, max_per_minute=2, clock=clock)
        trace = make_trace()

        assert throttle.check("ERROR", "boom", "app.x", trace).send
        for _ in range(100):
            throttle.check("ERROR", "boom", "app.x", trace)

        # One budget slot was used, so a different fault still gets through.
        assert throttle.check("ERROR", "other", "app.x", make_trace(KeyError)).send


class TestStateBounds:
    def test_signature_table_stays_bounded(self):
        from hibiki_logger.throttle import MAX_TRACKED_SIGNATURES

        clock = FakeClock()
        throttle = DiscordThrottle(
            dedup_window=300, max_per_minute=10**9, clock=clock
        )
        for i in range(MAX_TRACKED_SIGNATURES * 3):
            clock.advance(0.001)
            throttle.check("ERROR", f"distinct {i}", "app.x")

        assert len(throttle._windows) <= MAX_TRACKED_SIGNATURES

    def test_reset_clears_state(self):
        throttle = DiscordThrottle(dedup_window=300, max_per_minute=5)
        throttle.check("ERROR", "a", "app.x")
        throttle.reset()
        assert throttle.check("ERROR", "a", "app.x").send is True


class TestFailedSends:
    """A send that never landed must not suppress the next occurrence."""

    def test_failed_send_releases_the_dedup_window(self):
        clock = FakeClock()
        throttle = DiscordThrottle(dedup_window=300, max_per_minute=1000, clock=clock)
        trace = make_trace()

        first = throttle.check("ERROR", "boom", "app.x", trace)
        assert first.send is True
        throttle.record_failure(first)

        second = throttle.check("ERROR", "boom", "app.x", trace)
        assert second.send is True

    def test_failed_send_still_consumes_budget(self):
        """Retries of an undeliverable fault stay bounded by the budget."""
        clock = FakeClock()
        throttle = DiscordThrottle(dedup_window=300, max_per_minute=3, clock=clock)
        trace = make_trace()

        attempts = 0
        for _ in range(100):
            clock.advance(0.01)
            decision = throttle.check("ERROR", "boom", "app.x", trace)
            if decision.send:
                attempts += 1
                throttle.record_failure(decision)

        assert attempts == 3

    def test_failed_send_preserves_the_suppressed_count(self):
        clock = FakeClock()
        throttle = DiscordThrottle(dedup_window=10, max_per_minute=1000, clock=clock)
        trace = make_trace()

        throttle.check("ERROR", "boom", "app.x", trace)
        for _ in range(5):
            throttle.check("ERROR", "boom", "app.x", trace)

        clock.advance(11)
        failed = throttle.check("ERROR", "boom", "app.x", trace)
        assert failed.suppressed == 5
        throttle.record_failure(failed)

        # The count was never delivered, so it must survive to the next send.
        retry = throttle.check("ERROR", "boom", "app.x", trace)
        assert retry.send is True
        assert retry.suppressed == 5

    def test_failed_send_preserves_the_dropped_count(self):
        clock = FakeClock()
        throttle = DiscordThrottle(dedup_window=300, max_per_minute=2, clock=clock)

        throttle.check("ERROR", "a", "app.x")
        throttle.check("ERROR", "b", "app.x")
        for i in range(10):
            throttle.check("ERROR", f"shed {i}", "app.x")

        clock.advance(61)
        failed = throttle.check("ERROR", "c", "app.x")
        assert failed.dropped == 10
        throttle.record_failure(failed)

        recovered = throttle.check("ERROR", "d", "app.x")
        assert recovered.dropped == 10

    def test_occurrences_during_the_send_are_not_lost(self):
        """Repeats arriving while a send is in flight land on its window.

        The send then fails, so those occurrences were neither delivered
        nor reported. Rolling the window back must carry them forward
        rather than discard them.
        """
        clock = FakeClock()
        throttle = DiscordThrottle(dedup_window=300, max_per_minute=1000, clock=clock)
        trace = make_trace()

        in_flight = throttle.check("ERROR", "boom", "app.x", trace)
        assert in_flight.send is True
        for _ in range(9):
            throttle.check("ERROR", "boom", "app.x", trace)

        throttle.record_failure(in_flight)

        recovered = throttle.check("ERROR", "boom", "app.x", trace)
        assert recovered.send is True
        assert recovered.suppressed == 9

    def test_occurrences_during_the_send_merge_with_an_earlier_count(self):
        clock = FakeClock()
        throttle = DiscordThrottle(dedup_window=10, max_per_minute=1000, clock=clock)
        trace = make_trace()

        throttle.check("ERROR", "boom", "app.x", trace)
        for _ in range(5):
            throttle.check("ERROR", "boom", "app.x", trace)

        clock.advance(11)
        failed = throttle.check("ERROR", "boom", "app.x", trace)
        assert failed.suppressed == 5
        for _ in range(3):
            throttle.check("ERROR", "boom", "app.x", trace)
        throttle.record_failure(failed)

        recovered = throttle.check("ERROR", "boom", "app.x", trace)
        assert recovered.send is True
        assert recovered.suppressed == 8

    def test_record_failure_ignores_a_no_send_decision(self):
        throttle = DiscordThrottle(dedup_window=300, max_per_minute=1)
        throttle.check("ERROR", "a", "app.x")
        suppressed = throttle.check("ERROR", "a", "app.x")
        assert suppressed.send is False
        throttle.record_failure(suppressed)  # must not raise or corrupt state


class TestDisablingDedup:
    def test_zero_window_disables_deduplication(self):
        clock = FakeClock()
        throttle = DiscordThrottle(dedup_window=0, max_per_minute=1000, clock=clock)
        trace = make_trace()

        sends = sum(
            1 for _ in range(10) if throttle.check("ERROR", "boom", "app.x", trace).send
        )
        assert sends == 10
