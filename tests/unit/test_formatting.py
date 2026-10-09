from datetime import date

import pytest

from arcivo.domain.formatting import (
    human_duration,
    human_size,
    parse_date,
    parse_duration,
    parse_size,
)


@pytest.mark.parametrize("text,expected", [("50MB", 52428800), ("1.5gb", 1610612736), ("100", 100), ("2k", 2048), ("۵MB", 5242880)])
def test_parse_size(text, expected):
    assert parse_size(text) == expected


@pytest.mark.parametrize("text,expected", [("90", 90), ("1:30", 90), ("1h2m3s", 3723), ("5m", 300), ("1:00:00", 3600)])
def test_parse_duration(text, expected):
    assert parse_duration(text) == expected


def test_human():
    assert human_size(0) == "0 B"
    assert human_size(1536) == "1.5 KB"
    assert human_duration(3723) == "1:02:03"
    assert human_duration(65) == "1:05"


def test_parse_date_ranges():
    assert parse_date("2025") == (date(2025, 1, 1), date(2025, 12, 31))
    assert parse_date("2024-02") == (date(2024, 2, 1), date(2024, 2, 29))
    assert parse_date("2025/03/04") == (date(2025, 3, 4), date(2025, 3, 4))
