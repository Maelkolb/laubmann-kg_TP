from laubmann_kg.pipeline import run_pipeline


def test_pipeline_builds_entries_and_observations(sample_config) -> None:
    result = run_pipeline(sample_config)
    assert len(result.entries) == 3

    by_id = {e.entry_id: e for e in result.entries}
    assert by_id["L02-e0001"].entry_date == "1918-04-07"
    # The weather-only entry yields no observation.
    assert by_id["L02-e0003"].observations == []
    # München resolves to seeded coordinates.
    muenchen = next(p for p in result.places.values() if p.canonical == "München")
    assert muenchen.lat is not None


def test_pipeline_is_deterministic(sample_config) -> None:
    first = [o.uid for o in run_pipeline(sample_config).observations]
    second = [o.uid for o in run_pipeline(sample_config).observations]
    assert first == second


def test_concurrent_extraction_matches_sequential(sample_config) -> None:
    sequential = run_pipeline(sample_config)
    sample_config["extraction"]["concurrency"] = 4
    concurrent = run_pipeline(sample_config)
    assert [e.entry_id for e in concurrent.entries] == [e.entry_id for e in sequential.entries]
    assert [o.uid for o in concurrent.observations] == [o.uid for o in sequential.observations]


def test_input_dir_prefers_cleaned_multimodal_catalogue(tmp_path) -> None:
    from laubmann_kg.pipeline import _resolve_corpus
    (tmp_path / "entries.csv").write_text("x", encoding="utf-8")
    assert _resolve_corpus({}, tmp_path) == (tmp_path / "entries.csv", None)
    (tmp_path / "multimodal.md").write_text("raw", encoding="utf-8")
    assert _resolve_corpus({}, tmp_path)[1] == tmp_path / "multimodal.md"
    (tmp_path / "multimodal_clean.md").write_text("clean", encoding="utf-8")
    assert _resolve_corpus({}, tmp_path)[1] == tmp_path / "multimodal_clean.md"
