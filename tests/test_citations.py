from laubmann_kg.extraction.citations import extract_citations


def test_extracts_real_attributions() -> None:
    assert [c.verbatim for c in extract_citations("Brut, teste Förster Huber, bestätigt")] \
        == ["teste Förster Huber"]
    assert any("vgl. Tagebuch" in c.verbatim for c in extract_citations("Zug, vgl. Tagebuch I."))
    assert any("Angabe von Müller" in c.verbatim
               for c in extract_citations("nach Angabe von Müller gesehen"))


def test_ignores_travel_foraging_and_loudness() -> None:
    for text in ("nach München geflogen", "nach Nahrung suchend", "laut rufend überhin fliegend"):
        assert extract_citations(text) == [], text
