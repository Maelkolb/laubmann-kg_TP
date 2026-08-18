"""Taxon linking against the GBIF backbone (resolver names + LLM fallback).

Candidate binomials come from the taxon resolver or — for unresolved vernacular
names — from the revived taxon_normalization prompt; every candidate is verified
against the GBIF species/match API before anything is applied. External keys and
canonical names therefore only ever come from GBIF, never from the LLM.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import replace
from pathlib import Path
from typing import Optional

from laubmann_kg.kg.model import HIGHER_RANKS
from laubmann_kg.linking import http, review
from laubmann_kg.linking.cache import JsonCache

logger = logging.getLogger(__name__)

GBIF_MATCH_URL = "https://api.gbif.org/v1/species/match"
GBIF_SPECIES_NS = "https://www.gbif.org/species/"
TAXON_REVIEW_FIELDS = ["vernacular_de", "taxon_uid", "n_observations",
    "current_scientific_name", "llm_scientific_name", "llm_confidence",
    "gbif_match_type", "gbif_confidence", "gbif_key", "gbif_canonical_name",
    "status", "decision"]

_SCHEMA_PATH = Path("schemas/taxon_normalization.schema.json")
_ACCEPT_RANKS = ("SPECIES", "SUBSPECIES")
# taxon.rank (model-provided) -> GBIF ranks accepted for an EXACT/FUZZY link.
# A genus- or family-level name IS the taxon the diarist meant, so the match at
# that rank is exact, not a broad anchor. Everything else keeps the species gate.
_ACCEPT_RANKS_BY_ITEM_RANK = {
    "genus": ("GENUS",),
    "family": ("FAMILY",),
}
DEFAULT_TAXON_CLASS = "Aves"


def higher_taxonomy(response: Optional[dict]) -> tuple[tuple[str, str], ...]:
    """GBIF classification of a species/match response as ((rank, name), ...)
    in HIGHER_RANKS order — only the ranks GBIF filled in (a HIGHERRANK match
    at genus level has no species, an unmatched response nothing at all).
    Never fabricates a rank; tolerates missing keys."""
    if not isinstance(response, dict):
        return ()
    out = []
    for rank in HIGHER_RANKS:
        name = response.get(rank)
        if isinstance(name, str) and name.strip():
            out.append((rank, name.strip()))
    return tuple(out)


def gbif_cache_key(scientific_name: str, taxon_class: Optional[str] = DEFAULT_TAXON_CLASS) -> str:
    """Cache key for a species/match lookup. Bird lookups keep the legacy
    ``match:<name>`` form so existing caches stay valid; any other class (or
    none, for is_bird == False) is keyed ``match:<class>:<name>``."""
    name = scientific_name.strip().lower()
    if taxon_class == DEFAULT_TAXON_CLASS:
        return "match:" + name
    return f"match:{(taxon_class or 'any').strip().lower()}:{name}"


def _cached_higher_taxonomy(cache: JsonCache, canonical: Optional[str],
                            is_bird: Optional[bool]) -> tuple[tuple[str, str], ...]:
    """Classification for a reviewed name from the GBIF cache only (no
    network). Tries the class-specific key first, then the class-less one."""
    if not canonical:
        return ()
    classes = [None] if is_bird is False else [DEFAULT_TAXON_CLASS, None]
    for taxon_class in classes:
        key = gbif_cache_key(canonical, taxon_class)
        if key in cache:
            return higher_taxonomy(cache.get(key))
    return ()


class GbifClient:
    def __init__(self, cache: JsonCache, offline: bool = False, sleep_s: float = 0.2) -> None:
        self.cache = cache
        self.offline = offline
        self.sleep_s = sleep_s

    def match(self, scientific_name: str,
              taxon_class: Optional[str] = DEFAULT_TAXON_CLASS) -> Optional[dict]:
        """``taxon_class`` narrows the backbone search (default Aves); pass
        None for a non-bird taxon (kingdom Animalia only)."""
        key = gbif_cache_key(scientific_name, taxon_class)
        if key in self.cache:
            return self.cache.get(key)
        if self.offline:
            return None
        # kingdom/class narrow the backbone search and disambiguate homonym
        # genera (bare "Oenanthe" -> the bird, not the plant).
        params = {"name": scientific_name, "kingdom": "Animalia"}
        if taxon_class:
            params["class"] = taxon_class
        response = http.get_json(GBIF_MATCH_URL, params)
        if response is None:
            return None
        time.sleep(self.sleep_s)
        self.cache.put(key, response)
        return response


def build_llm_proposer(cfg: dict):
    """cfg = linking.taxa.llm. Returns ``propose(vernacular_de, context) ->
    Optional[{"scientific_name": str|None, "confidence": float}]`` or None when
    disabled/unavailable (callers mark rows llm_unavailable)."""
    cfg = cfg or {}
    if not cfg.get("enabled", True):
        return None
    from laubmann_kg.llm.cache import LLMCache, cache_key
    from laubmann_kg.llm.clients import build_client
    from laubmann_kg.llm.prompts import PromptLibrary
    from laubmann_kg.llm.structured_output import extract_json, parse_structured

    llm_cache = LLMCache(Path(cfg.get("cache_dir", "data/cache/linking_llm")))
    try:
        client = build_client(
            cache=llm_cache,
            config={
                "backend": cfg.get("provider", "google"),
                "model": cfg.get("model"),
                "api_key_env": cfg.get("api_key_env", "GOOGLE_API_KEY"),
                "temperature": cfg.get("temperature", 0.0),
                # small JSON answer, but thinking tokens may count against the cap
                "max_output_tokens": cfg.get("max_output_tokens", 1024),
                "timeout": cfg.get("timeout", 60),
                "thinking_level": cfg.get("thinking_level"),
                "retry_attempts": cfg.get("retry_attempts", 2),
                "retry_backoff": cfg.get("retry_backoff", 2.0),
            })
    except Exception as exc:  # noqa: BLE001 - missing SDK/backend: degrade, don't abort
        logger.warning("taxon LLM proposer unavailable: %s", exc)
        return None
    prompts = PromptLibrary(Path(cfg.get("prompt_dir", "prompts")))
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    schema.pop("$schema", None)

    def _to_proposal(raw: str) -> Optional[dict]:
        try:
            data = parse_structured(raw, schema)
        except Exception:  # noqa: BLE001 - tolerant envelope; this mapper enforces
            data = extract_json(raw)
        if not isinstance(data, dict):
            return None
        name = (str(data.get("scientific_name") or "")).strip() or None
        try:
            confidence = float(data.get("confidence"))
        except (TypeError, ValueError):
            confidence = 0.0
        return {"scientific_name": name,
                "confidence": min(max(confidence, 0.0), 1.0)}

    def propose(vernacular_de: str, context: str) -> Optional[dict]:
        prompt = prompts.render("taxon_normalization",
                                vernacular_de=vernacular_de, context=context)
        try:
            return _to_proposal(client.complete(prompt))
        except Exception as exc:  # noqa: BLE001
            logger.warning("taxon LLM proposal failed for %r: %s", vernacular_de, exc)
            return None

    def peek(vernacular_de: str, context: str) -> Optional[dict]:
        """Cached proposal without any LLM/network work; None == not cached
        (a cached-but-unparseable answer still counts as cached — propose()
        would return it without a network call)."""
        raw = llm_cache.get(cache_key(
            getattr(client, "model", ""),
            prompts.render("taxon_normalization",
                           vernacular_de=vernacular_de, context=context)))
        if raw is None:
            return None
        try:
            proposal = _to_proposal(raw)
        except Exception:  # noqa: BLE001
            proposal = None
        return proposal or {"scientific_name": None, "confidence": 0.0}

    propose.peek = peek
    return propose


def _collect_taxa(result) -> list[dict]:
    """Distinct taxa by lowercased vernacular, ordered (-n_observations, name);
    context = up to 3 distinct verbatim notes in entry order. ``rank`` and
    ``is_bird`` are the first non-None values seen (model-provided)."""
    by_name: dict[str, dict] = {}
    for entry in result.entries:
        for obs in entry.observations:
            info = by_name.setdefault(obs.taxon.vernacular_de.lower(), {
                "vernacular_de": obs.taxon.vernacular_de,
                "taxon_uid": obs.taxon.uid,
                "scientific_name": None,
                "rank": None,
                "is_bird": None,
                "n_observations": 0,
                "notes": [],
            })
            if info["scientific_name"] is None:
                info["scientific_name"] = obs.taxon.scientific_name
            if info["rank"] is None:
                info["rank"] = getattr(obs.taxon, "rank", None)
            if info["is_bird"] is None:
                info["is_bird"] = getattr(obs.taxon, "is_bird", None)
            info["n_observations"] += 1
            if (obs.verbatim_notes and len(info["notes"]) < 3
                    and obs.verbatim_notes not in info["notes"]):
                info["notes"].append(obs.verbatim_notes)
    items = sorted(by_name.values(),
                   key=lambda i: (-i["n_observations"], i["vernacular_de"]))
    for item in items:
        item["context"] = "; ".join(item.pop("notes"))
    return items


def link_taxa(result, cfg: dict, cache: JsonCache, offline: bool) -> tuple[int, list[dict]]:
    cfg = cfg or {}
    gbif_cfg = cfg.get("gbif", {}) or {}
    min_confidence = float(gbif_cfg.get("min_confidence", 90))
    fuzzy_min_confidence = float(gbif_cfg.get("fuzzy_min_confidence", 95))
    llm_cfg = cfg.get("llm", {}) or {}
    llm_min_confidence = float(llm_cfg.get("min_confidence", 0.7))
    limit = int(cfg.get("limit", 0) or 0)
    client = GbifClient(cache, offline=offline, sleep_s=float(cfg.get("sleep", 0.2)))

    reviewed: dict[str, tuple[int, Optional[str], str]] = {}
    if cfg.get("reviewed_csv"):
        for row in review.load_reviewed(cfg["reviewed_csv"]):
            name = (row.get("vernacular_de") or "").strip()
            try:
                key = int(row.get("gbif_key") or "")
            except ValueError:
                continue
            if name:
                # blank match type: legacy CSVs predating the column -> EXACT
                reviewed[name.lower()] = (
                    key, (row.get("gbif_canonical_name") or "").strip() or None,
                    (row.get("gbif_match_type") or "").strip() or "EXACT")

    llm_requested = bool(llm_cfg.get("enabled", True)) and not offline
    proposer = build_llm_proposer(llm_cfg) if llm_requested else None
    llm_unavailable = llm_requested and proposer is None

    rows: list[dict] = []
    links: dict[str, dict] = {}  # vernacular.lower() -> dataclasses.replace kwargs
    uncached = 0
    for item in _collect_taxa(result):
        try:
            low = item["vernacular_de"].lower()
            row = {
                "vernacular_de": item["vernacular_de"],
                "taxon_uid": item["taxon_uid"],
                "n_observations": item["n_observations"],
                "current_scientific_name": item["scientific_name"] or "",
                "llm_scientific_name": "", "llm_confidence": "",
                "gbif_match_type": "", "gbif_confidence": "",
                "gbif_key": "", "gbif_canonical_name": "",
                "status": "", "decision": "",
            }
            if low in reviewed:
                key, canonical, match_type = reviewed[low]
                kwargs = {"gbif_key": key, "gbif_match_type": match_type,
                          "gbif_canonical_name": canonical,
                          "match_method": "review"}
                # classification only from an already-cached GBIF response
                # (adjudication never triggers network work)
                taxonomy = _cached_higher_taxonomy(cache, canonical, item.get("is_bird"))
                if taxonomy:
                    kwargs["higher_taxonomy"] = taxonomy
                # an adjudicated species-level name may fill an unresolved
                # slot; a HIGHERRANK genus anchor never becomes a species name
                if (item["scientific_name"] is None and canonical
                        and match_type in ("EXACT", "FUZZY")):
                    kwargs["scientific_name"] = canonical
                links[low] = kwargs
                row.update(gbif_key=key, gbif_match_type=match_type,
                           gbif_canonical_name=canonical or "", status="reviewed")
                rows.append(row)
                continue
            candidate = item["scientific_name"]
            # the class parameter only applies to birds; a taxon the model
            # marked as non-bird is matched against kingdom Animalia alone
            taxon_class = DEFAULT_TAXON_CLASS if item.get("is_bird") is not False else None
            accept_ranks = _ACCEPT_RANKS_BY_ITEM_RANK.get(item.get("rank"), _ACCEPT_RANKS)
            # limit caps UNCACHED lookups per run: a name consumes budget only
            # when real LLM/network work would fire, so capped runs progress
            # across restarts once earlier names are fully cached.
            if candidate is not None:
                needs_lookup = gbif_cache_key(candidate, taxon_class) not in cache
            elif proposer is None:
                needs_lookup = False          # no LLM available -> nothing fires
            else:
                peek = getattr(proposer, "peek", None)
                cached = peek(item["vernacular_de"], item["context"]) if peek else None
                if cached is None:
                    needs_lookup = True       # LLM call (or unknown cache state)
                else:
                    proposed = cached.get("scientific_name")
                    needs_lookup = bool(proposed) and (
                        gbif_cache_key(proposed, taxon_class) not in cache)
            if limit and needs_lookup and uncached >= limit:
                continue
            if needs_lookup:
                uncached += 1
            from_llm = False
            llm_accepted = True
            if candidate is None:
                if proposer is None:
                    row["status"] = "llm_unavailable" if llm_unavailable else "no_match"
                    rows.append(row)
                    continue
                proposal = proposer(item["vernacular_de"], item["context"])
                if not proposal or not proposal.get("scientific_name"):
                    row["status"] = "no_match"
                    rows.append(row)
                    continue
                candidate = proposal["scientific_name"]
                from_llm = True
                # below-threshold proposals are still GBIF-checked to enrich
                # the review row, but never linked
                llm_accepted = proposal["confidence"] >= llm_min_confidence
                row["llm_scientific_name"] = candidate
                row["llm_confidence"] = proposal["confidence"]
            response = client.match(candidate, taxon_class=taxon_class)
            if response is None:
                row["status"] = "error"  # uncached -> retried next run
                rows.append(row)
                continue
            match_type = response.get("matchType") or "NONE"
            confidence = response.get("confidence") or 0
            usage_key = response.get("usageKey")
            accepted_key = usage_key
            if response.get("synonym") and response.get("acceptedUsageKey"):
                accepted_key = response.get("acceptedUsageKey")
            canonical = response.get("canonicalName") or ""
            # rank gate: species-level items accept SPECIES/SUBSPECIES; a
            # genus-/family-level item accepts a match AT that rank (the taxon
            # IS the genus/family -> exactMatch/closeMatch + taxonID)
            rank_ok = (response.get("rank") or "").upper() in accept_ranks
            row.update(gbif_match_type=match_type, gbif_confidence=confidence,
                       gbif_key="" if accepted_key is None else accepted_key,
                       gbif_canonical_name=canonical)
            linked = False
            if llm_accepted and accepted_key is not None:
                if match_type == "EXACT" and confidence >= min_confidence and rank_ok:
                    linked = True
                elif match_type == "FUZZY" and confidence >= fuzzy_min_confidence and rank_ok:
                    linked = True
                elif match_type == "HIGHERRANK" and not from_llm:
                    # resolver name anchored at genus level: broadMatch only,
                    # no taxonID, no name backfill. LLM + HIGHERRANK is double
                    # uncertainty -> review only.
                    links[low] = {"gbif_key": accepted_key,
                                  "gbif_match_type": "HIGHERRANK",
                                  "gbif_canonical_name": canonical or None,
                                  "higher_taxonomy": higher_taxonomy(response)}
                    row["status"] = "linked-broad"
                    rows.append(row)
                    continue
            if linked:
                kwargs = {"gbif_key": accepted_key, "gbif_match_type": match_type,
                          "gbif_canonical_name": canonical or None,
                          "higher_taxonomy": higher_taxonomy(response)}
                if from_llm:
                    # the emitted binomial is the VERIFIED form — the LLM never
                    # mints a name; resolver names are never overwritten
                    kwargs.update(scientific_name=canonical or candidate,
                                  match_method="llm+gbif", note=None)
                links[low] = kwargs
                row["status"] = "linked"
            else:
                row["status"] = "review"
            rows.append(row)
        except Exception as exc:  # noqa: BLE001 - linking must never abort the pipeline
            logger.warning("taxon linking failed for %r: %s",
                           item.get("vernacular_de"), exc)

    # collect-then-apply: uid is vernacular-derived, so enrichment via replace
    # never forks node identity
    for entry in result.entries:
        for obs in entry.observations:
            kwargs = links.get(obs.taxon.vernacular_de.lower())
            if kwargs:
                obs.taxon = replace(obs.taxon, **kwargs)
    return len(links), rows
