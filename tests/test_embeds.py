import traceback

from hibiki_logger.embeds import (
    CRITICAL_COLOR,
    DESCRIPTION_LIMIT,
    ERROR_COLOR,
    FIELD_VALUE_LIMIT,
    TOTAL_LIMIT,
    WARNING_COLOR,
    _embed_length,
    build_error_embed,
    build_footer,
    level_color,
    truncate_middle,
)


def deep_traceback(frames=400):
    """A traceback long enough to exceed Discord's description limit.

    Real recursion will not do: Python collapses repeated frames into
    "[Previous line repeated N more times]", so a deep stack still prints
    short. Distinct frames are spliced into a genuine traceback instead,
    preserving the real header first and exception line last.
    """

    def raiser():
        raise ValueError("the innermost boom")

    try:
        raiser()
    except ValueError as e:
        real = "".join(traceback.format_exception(type(e), e, e.__traceback__))

    lines = real.splitlines(keepends=True)
    header, inner, exc_line = lines[0], lines[1:-1], lines[-1]
    filler = "".join(
        f'  File "/app/module_{i}.py", line {i}, in handler_{i}\n'
        f"    do_work_{i}()\n"
        for i in range(frames)
    )
    return header + filler + "".join(inner) + exc_line


class TestLevelColor:
    def test_known_levels(self):
        assert level_color("WARNING") == WARNING_COLOR
        assert level_color("ERROR") == ERROR_COLOR
        assert level_color("CRITICAL") == CRITICAL_COLOR

    def test_case_insensitive(self):
        assert level_color("error") == ERROR_COLOR

    def test_unknown_level_has_a_colour(self):
        assert isinstance(level_color("NOTALEVEL"), int)


class TestTruncateMiddle:
    def test_short_text_untouched(self):
        assert truncate_middle("hello", 100) == "hello"

    def test_keeps_head_and_tail(self):
        text = "START" + ("x" * 5000) + "END"
        result = truncate_middle(text, 200)
        assert len(result) <= 200
        assert result.startswith("START")
        assert result.endswith("END")

    def test_zero_limit(self):
        assert truncate_middle("anything", 0) == ""


class TestBuildFooter:
    def test_none_when_nothing_to_report(self):
        assert build_footer(0, 0) is None

    def test_suppression_wording(self):
        assert build_footer(142, 0) == "142 further occurrences suppressed."

    def test_singular_wording(self):
        assert build_footer(1, 0) == "1 further occurrence suppressed."

    def test_combines_both_counts(self):
        footer = build_footer(5, 3)
        assert "5 further occurrences suppressed." in footer
        assert "3 older queued alerts dropped." in footer


class TestBuildErrorEmbed:
    def test_omits_unset_fields(self):
        embed = build_error_embed("ERROR", "msg", "app.x")
        names = [f["name"] for f in embed.get("fields", [])]
        assert names == ["Logger"]

    def test_includes_set_context_fields(self):
        embed = build_error_embed(
            "ERROR", "msg", "app.x", user_id="u1", path="/orders", method="POST"
        )
        fields = {f["name"]: f["value"] for f in embed["fields"]}
        assert fields == {
            "Logger": "app.x",
            "User ID": "u1",
            "Path": "/orders",
            "Method": "POST",
        }

    def test_blank_strings_count_as_unset(self):
        embed = build_error_embed("ERROR", "msg", "app.x", user_id="   ")
        names = [f["name"] for f in embed["fields"]]
        assert "User ID" not in names

    def test_has_timestamp_and_colour(self):
        embed = build_error_embed("CRITICAL", "msg", "app.x")
        assert embed["color"] == CRITICAL_COLOR
        assert "timestamp" in embed

    def test_oversized_traceback_stays_within_discord_limits(self):
        trace = deep_traceback()
        assert len(trace) > DESCRIPTION_LIMIT

        embed = build_error_embed(
            "ERROR",
            "request failed",
            "app.orders",
            trace=trace,
            user_id="u1",
            path="/orders",
            method="POST",
            suppressed_count=142,
        )

        assert len(embed["description"]) <= DESCRIPTION_LIMIT
        assert _embed_length(embed) <= TOTAL_LIMIT
        for field in embed["fields"]:
            assert len(field["value"]) <= FIELD_VALUE_LIMIT

    def test_truncated_traceback_keeps_exception_line(self):
        """The exception line and innermost frames are what diagnose the fault."""
        trace = deep_traceback()
        embed = build_error_embed("ERROR", "request failed", "app.x", trace=trace)
        assert "ValueError: the innermost boom" in embed["description"]

    def test_truncated_traceback_keeps_the_header(self):
        trace = deep_traceback()
        embed = build_error_embed("ERROR", "request failed", "app.x", trace=trace)
        assert "Traceback (most recent call last)" in embed["description"]

    def test_suppression_count_goes_in_footer(self):
        embed = build_error_embed(
            "ERROR", "msg", "app.x", suppressed_count=142
        )
        assert "142 further occurrences suppressed." in embed["footer"]["text"]
        assert "142" not in embed["description"]

    def test_no_footer_key_when_nothing_suppressed(self):
        embed = build_error_embed("ERROR", "msg", "app.x")
        assert "footer" not in embed

    def test_huge_message_without_trace_is_truncated(self):
        embed = build_error_embed("ERROR", "x" * 20000, "app.x")
        assert len(embed["description"]) <= DESCRIPTION_LIMIT
        assert _embed_length(embed) <= TOTAL_LIMIT

    def test_huge_message_and_huge_trace_together(self):
        embed = build_error_embed(
            "ERROR", "x" * 10000, "app.x", trace="y" * 10000
        )
        assert len(embed["description"]) <= DESCRIPTION_LIMIT
        assert _embed_length(embed) <= TOTAL_LIMIT

    def test_empty_message(self):
        embed = build_error_embed("ERROR", "", "app.x")
        assert embed["description"] == ""


class TestTruncationCountAccuracy:
    """The count in the marker is the one number the marker exists to report."""

    def test_reported_count_matches_characters_actually_dropped(self):
        import re

        pattern = re.compile(r"\.\.\. (\d+) characters truncated \.\.\.")
        for limit in range(1, 300):
            for size in (100, 137, 1000, 10000):
                text = "A" * size
                result = truncate_middle(text, limit)
                match = pattern.search(result)
                if not match:
                    continue
                kept = len(result) - len(match.group(0)) - 2  # two newlines
                assert int(match.group(1)) == size - kept, (
                    f"limit={limit} size={size}"
                )

    def test_result_never_exceeds_the_limit(self):
        for limit in range(1, 300):
            assert len(truncate_middle("A" * 5000, limit)) <= limit
