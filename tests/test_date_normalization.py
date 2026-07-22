from laubmann_kg.normalization.dates import normalize_date, parse_german_date


def test_prefers_iso_date_norm() -> None:
    assert normalize_date("7. April 1917", "1917-04-07") == "1917-04-07"


def test_falls_back_to_raw_when_norm_missing() -> None:
    assert normalize_date("10. April 1917", None) == "1917-04-10"


def test_parses_german_month_names() -> None:
    assert parse_german_date("29. Mai 1925") == "1925-05-29"
    assert parse_german_date("1. Jänner 1920") == "1920-01-01"


def test_rejects_invalid_dates() -> None:
    assert parse_german_date("30. Februar 1918") is None
    assert normalize_date(None, "not-a-date") is None
    assert normalize_date("kein Datum", None) is None
