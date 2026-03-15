"""Tests for round-robin counsellor assignment."""

import pytest

from backend.workflows.counsellor_assignment import get_next_counsellor, reset_index


@pytest.fixture(autouse=True)
def reset_counter():
    """Reset the round-robin counter before each test to ensure isolation."""
    reset_index()
    yield
    reset_index()


class TestRoundRobin:
    def test_single_counsellor_always_returns_same(self):
        counsellors = ["+919111111111"]
        assert get_next_counsellor(counsellors) == "+919111111111"
        assert get_next_counsellor(counsellors) == "+919111111111"

    def test_two_counsellors_alternate(self):
        counsellors = ["+919111111111", "+919222222222"]
        first = get_next_counsellor(counsellors)
        second = get_next_counsellor(counsellors)
        assert first != second
        assert first in counsellors
        assert second in counsellors

    def test_wraps_around_after_exhausting_list(self):
        counsellors = ["A", "B", "C"]
        results = [get_next_counsellor(counsellors) for _ in range(6)]
        assert results == ["A", "B", "C", "A", "B", "C"]

    def test_empty_list_raises_value_error(self):
        with pytest.raises(ValueError, match="No counsellors"):
            get_next_counsellor([])

    def test_reset_restarts_from_first(self):
        counsellors = ["X", "Y"]
        get_next_counsellor(counsellors)  # X
        get_next_counsellor(counsellors)  # Y
        reset_index()
        assert get_next_counsellor(counsellors) == "X"

    def test_three_counsellors_full_cycle(self):
        counsellors = ["C1", "C2", "C3"]
        seen = {get_next_counsellor(counsellors) for _ in range(3)}
        assert seen == {"C1", "C2", "C3"}
