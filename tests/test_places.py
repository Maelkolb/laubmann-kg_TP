from laubmann_kg.normalization.places import normalize_place, rejection_reason


def test_gazetteer_place_gets_coordinates() -> None:
    p = normalize_place("München")
    assert p is not None and p.name == "München"
    assert p.lat == 48.1374 and p.long == 11.5755


def test_elevation_and_descriptor_tails_are_stripped() -> None:
    assert normalize_place("Oberstdorf 843 m").name == "Oberstdorf"
    assert normalize_place("Kochel. Herzogstandhaus 1555 m").name == "Kochel"


def test_naming_variants_fold_to_one_canonical() -> None:
    assert normalize_place("Dießen").name == "Dießen am Ammersee"
    assert normalize_place("Dießen am Ammersee").name == "Dießen am Ammersee"
    assert normalize_place("Kochel am Kochelsee").name == "Kochel"


def test_unseeded_locality_is_kept_without_coordinates() -> None:
    p = normalize_place("Bernbacher Moos")
    assert p is not None and p.name == "Bernbacher Moos" and p.lat is None


def test_bird_name_is_rejected_not_a_place() -> None:
    assert normalize_place("Rauchschwalben") is None
    assert rejection_reason("Rauchschwalben") == "bird"


def test_corpus_garbage_is_rejected() -> None:
    assert normalize_place("Rauhfutter") is None
    assert rejection_reason("Rauhfutter") == "garbage"


def test_empty_is_rejected() -> None:
    assert normalize_place("  ") is None
    assert rejection_reason(None) == "empty"
