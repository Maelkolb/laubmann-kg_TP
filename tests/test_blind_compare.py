import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "validation_ui" / "machine_review"))

from blind_compare import count_agrees, date_agrees, people  # noqa: E402


def test_count_same_number_or_both_empty():
    assert count_agrees("5", "5", "", "")
    assert count_agrees(None, "", "", "")
    assert not count_agrees("3", "", "", "")
    assert not count_agrees(None, "4", "", "")


def test_count_range_against_lower_bound_or_stored_range():
    assert count_agrees("6-8", "6", "", "")
    assert count_agrees("6-8", "7", "6", "8")
    assert not count_agrees("6-8", "7", "", "")


def test_count_absence_without_number():
    assert count_agrees(None, "0", "", "")


def test_date_entry_day_and_multi_day_entry():
    assert date_agrees("entry", "1934-08-20", "1934-08-20", "1934-08-20")
    assert date_agrees("entry", "1934-08-21", "1934-08-20/1934-08-22", "1934-08-20/1934-08-22")
    assert not date_agrees("entry", "1934-08-25", "1934-08-20", "1934-08-20")


def test_date_quoted_day_and_coarse_dates():
    assert date_agrees("1956-03-31", "1956-03-31", "1956-04-01", "1956-04-01")
    assert not date_agrees("1956-03-31", "1956-04-01", "1956-04-01", "1956-04-01")
    assert date_agrees("1922", "1922-06-01/1922-08-31", "1924-12-09", "1924-12-09")
    assert not date_agrees("1922", "1924-12-09", "1924-12-09", "1924-12-09")
    assert not date_agrees("undated", "1920-06-04", "1920-06-04", "1920-06-04")


def test_people_by_surname():
    assert people(["Walter Wüst"]) == people(["Dr. W. Wüst"])
    assert people(["Alfred Laubmann", "Einhard Bezzel"]) == {"laubmann", "bezzel"}
