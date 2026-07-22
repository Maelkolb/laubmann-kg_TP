from laubmann_kg.normalization.taxa import (
    LinksLongTaxonResolver,
    SeedTaxonResolver,
    find_taxa,
)


def test_find_taxa_matches_plural_and_inflected_forms() -> None:
    text = "einige Lachmöwen und ein Buchfink, dazu 3 Wildenten"
    names = {m.vernacular for m in find_taxa(text)}
    assert {"Lachmöwe", "Buchfink", "Wildente"} <= names


def test_find_taxa_handles_historic_v_w_spelling() -> None:
    assert any(m.vernacular in {"Lachmöwe", "Lachmöve"} for m in find_taxa("viele Lachmöven"))


def test_find_taxa_ignores_non_bird_words() -> None:
    assert find_taxa("Wetter trüb und kalt, starker Wind") == []


def test_seed_resolver_resolves_known_and_marks_unknown() -> None:
    resolver = SeedTaxonResolver()
    assert resolver.resolve("Buchfink").scientific_name == "Fringilla coelebs"
    unresolved = resolver.resolve("Fabelvogel")
    assert unresolved.scientific_name is None
    assert not unresolved.resolved


def test_links_long_resolver_falls_back_when_file_absent(tmp_path) -> None:
    resolver = LinksLongTaxonResolver(tmp_path / "missing.csv")
    assert resolver.resolve("Buchfink").scientific_name == "Fringilla coelebs"


def test_links_long_resolver_uses_trusted_rows(tmp_path) -> None:
    table = tmp_path / "links_long.csv"
    table.write_text(
        "species,scientific_name,reference_source,taxon_iri,resolve_confidence\n"
        "Kuckuck,Cuculus canorus,index_validated,https://gbif.org/1,0.95\n"
        "Star,Sturnus vulgaris,index_unresolved,,0.1\n",
        encoding="utf-8",
    )
    resolver = LinksLongTaxonResolver(table)
    trusted = resolver.resolve("Kuckuck")
    assert trusted.taxon_iri == "https://gbif.org/1"
    assert trusted.match_method.startswith("links_long")
    # Untrusted source falls back to the gazetteer, not the table's value.
    fallback = resolver.resolve("Star")
    assert fallback.scientific_name == "Sturnus vulgaris"
    assert "unbestätigt" in (fallback.note or "")
