"""Habitat linking: the diarist's habitat labels → EUNIS habitat classes.

The graph keeps one ``skos:Concept`` per habitat label as written (after
spelling resolution) — that is the source level. This stage adds the external
level: an LLM (Gemini, cached) reads each distinct label and names the best
EUNIS class (2012 classification, Eionet vocabulary
``http://eunis.eea.europa.eu/eunishabitats/<code>`` — an identifier: the EUNIS
web app is retired, the emitter adds rdfs:seeAlso to the Eionet DD concept
page and the BISE 2012 hierarchical view) with the kind of match —
``exact`` → ``skos:exactMatch``, ``close`` → ``skos:closeMatch``,
``broad`` → ``skos:broadMatch`` — and a confidence. Codes are validated against
``data/eunis_habitats.csv`` (5,282 classes); accepted matches
(confidence ≥ ``min_confidence``, default 0.7) are emitted on the habitat concept, the rest
go to ``review/habitat_link_review.csv`` (status linked | review | no_match)
where ``y`` / ``n`` decisions (``reviewed_csv``) override.

Labels are batched (``batch_size`` per prompt); every batch is one cached call
(``linking_cache/llm_habitats``), so re-runs are free and the extraction prompt
is untouched. Runs AFTER entity resolution, on the canonical labels.
"""

from __future__ import annotations

import csv
import json
import logging
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Optional

from laubmann_kg.linking import review

logger = logging.getLogger(__name__)

HABITAT_REVIEW_FIELDS = ["habitat_label", "n_obs", "status", "eunis_code", "eunis_label", "eunis_level", "match",
                         "confidence", "note", "eunis_uri", "decision"]
EUNIS_CSV = Path("data/eunis_habitats.csv")
EUNIS_SCHEME = "http://eunis.eea.europa.eu/eunishabitats/"
_SCHEMA_PATH = Path("schemas/habitat_eunis.schema.json")
_MATCHES = ("exact", "close", "broad")


class EunisVocabulary:
    """The EUNIS classes (code → row) and the level-1..3 list for the prompt."""

    def __init__(self, path: Path = EUNIS_CSV) -> None:
        self.path = Path(path)
        self.rows: dict[str, dict] = {}
        with self.path.open(newline="", encoding="utf-8") as h:
            for r in csv.DictReader(h):
                r["level"] = int(r["level"])
                self.rows[r["code"]] = r

    def get(self, code: Optional[str]) -> Optional[dict]:
        if not code:
            return None
        c = code.strip().upper().replace(" ", "")
        return self.rows.get(c)

    def ancestors(self, code: str) -> list[dict]:
        out = []
        r = self.rows.get(code)
        while r and r["parent"]:
            r = self.rows.get(r["parent"])
            if r:
                out.append(r)
        return out

    def prompt_list(self) -> str:
        lines = []
        for code, r in sorted(self.rows.items(), key=lambda kv: (kv[0][0], kv[1]["level"], kv[0])):
            if (code.startswith("A") and r["level"] > 2) or r["level"] > 3:
                continue
            lines.append(f"{code}\t{r['label']}")
        return "\n".join(lines)


def build_habitat_proposer(cfg: dict, vocab: EunisVocabulary):
    """cfg = linking.habitats.llm. Returns ``propose(labels) -> {label: item}``
    (items: code, match, confidence, note) or None when disabled/unavailable."""
    cfg = cfg or {}
    if not cfg.get("enabled", True):
        return None
    from laubmann_kg.llm.cache import LLMCache
    from laubmann_kg.llm.clients import build_client
    from laubmann_kg.llm.prompts import PromptLibrary
    from laubmann_kg.llm.structured_output import extract_json, parse_structured

    llm_cache = LLMCache(Path(cfg.get("cache_dir", "data/cache/linking_llm_habitats")))
    try:
        client = build_client(cache=llm_cache, config={
            "backend": cfg.get("provider", "google"), "model": cfg.get("model"),
            "api_key_env": cfg.get("api_key_env", "GOOGLE_API_KEY"), "temperature": cfg.get("temperature", 0.0),
            "max_output_tokens": cfg.get("max_output_tokens", 8192), "timeout": cfg.get("timeout", 120),
            "thinking_level": cfg.get("thinking_level"), "retry_attempts": cfg.get("retry_attempts", 2),
            "retry_backoff": cfg.get("retry_backoff", 2.0)})
    except Exception as exc:  # noqa: BLE001
        logger.warning("habitat LLM proposer unavailable: %s", exc)
        return None
    prompts = PromptLibrary(Path(cfg.get("prompt_dir", "prompts")))
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    schema.pop("$schema", None)
    eunis_list = vocab.prompt_list()

    def propose(labels: list[str]) -> dict[str, dict]:
        prompt = prompts.render("habitat_eunis", eunis_list=eunis_list, labels="\n".join(labels))
        try:
            raw = client.complete(prompt)
        except Exception as exc:  # noqa: BLE001
            logger.warning("habitat LLM proposal failed for a batch of %d: %s", len(labels), exc)
            return {}
        try:
            data = parse_structured(raw, schema)
        except Exception:  # noqa: BLE001
            data = extract_json(raw)
        items = (data or {}).get("items") if isinstance(data, dict) else None
        out: dict[str, dict] = {}
        if not isinstance(items, list):
            return out
        by_label = {str(i.get("label") or "").strip(): i for i in items if isinstance(i, dict)}
        for k, label in enumerate(labels):
            item = by_label.get(label) or (items[k] if k < len(items) and isinstance(items[k], dict) else None)
            if item is None:
                continue
            try:
                conf = float(item.get("confidence"))
            except (TypeError, ValueError):
                conf = 0.0
            out[label] = {"code": (str(item.get("code") or "").strip() or None),
                          "match": (str(item.get("match") or "").strip().lower() or None),
                          "confidence": min(max(conf, 0.0), 1.0), "note": (str(item.get("note") or "").strip())}
        return out

    return propose


def _collect_habitats(result) -> Counter:
    usage: Counter = Counter()
    for entry in result.entries:
        for obs in entry.observations:
            if obs.habitat is not None:
                usage[obs.habitat.label] += 1
    return usage


def link_habitats(result, cfg: dict, offline: bool) -> tuple[int, list[dict]]:
    """Attach EUNIS links to the Habitat objects (``eunis_code``, ``eunis_match``
    …); returns (n_linked, review rows)."""
    cfg = cfg or {}
    vocab = EunisVocabulary(Path(cfg.get("vocabulary", EUNIS_CSV)))
    min_conf = float(cfg.get("min_confidence", 0.7))
    review_conf = float(cfg.get("review_confidence", 0.4))
    batch_size = int(cfg.get("batch_size", 40))
    limit = int(cfg.get("limit", 0) or 0)
    usage = _collect_habitats(result)
    if not usage:
        return 0, []

    reviewed: dict[str, dict] = {}
    rejected: set[str] = set()
    if cfg.get("reviewed_csv"):
        for row in review.load_reviewed(cfg["reviewed_csv"]):
            reviewed[(row.get("habitat_label") or "").strip()] = row
        p = Path(cfg["reviewed_csv"])
        if p.exists():
            with p.open(newline="", encoding="utf-8") as h:
                for row in csv.DictReader(h):
                    if (row.get("decision") or "").strip().lower() in ("n", "no", "reject", "0"):
                        rejected.add((row.get("habitat_label") or "").strip())

    proposer = build_habitat_proposer(dict(cfg.get("llm") or {}), vocab) if not offline else None
    labels = [l for l, _ in usage.most_common()]
    if limit:
        labels = labels[:limit]
    todo = [l for l in labels if l not in reviewed]
    proposals: dict[str, dict] = {}
    if proposer is not None:
        for start in range(0, len(todo), batch_size):
            proposals.update(proposer(todo[start:start + batch_size]))
    elif todo:
        logger.warning("habitat linking: no LLM proposer (offline) — %d labels left unclassified", len(todo))

    rows: list[dict] = []
    links: dict[str, tuple[str, str]] = {}       # label -> (code, match)
    for label in labels:
        n = usage[label]
        base = {"habitat_label": label, "n_obs": n, "status": "", "eunis_code": "", "eunis_label": "", "eunis_level": "",
                "match": "", "confidence": "", "note": "", "eunis_uri": "", "decision": ""}
        if label in reviewed:
            r = reviewed[label]
            e = vocab.get(r.get("eunis_code"))
            if e:
                m = (r.get("match") or "close").lower()
                links[label] = (e["code"], m if m in _MATCHES else "close")
                rows.append({**base, "status": "reviewed", "eunis_code": e["code"], "eunis_label": e["label"], "eunis_level": e["level"],
                             "match": links[label][1], "confidence": "1.00", "eunis_uri": e["uri"], "decision": "y"})
                continue
        p = proposals.get(label)
        if p is None:
            rows.append({**base, "status": "no_match" if proposer is not None else "unclassified", "note": "" if proposer is not None else "no proposer"})
            continue
        e = vocab.get(p["code"]) if p.get("match") in _MATCHES else None
        if e is None:
            rows.append({**base, "status": "no_match", "match": p.get("match") or "", "confidence": f"{p['confidence']:.2f}",
                         "note": p.get("note") or ("unknown code " + str(p.get("code")) if p.get("code") else "")})
            continue
        status = "linked" if p["confidence"] >= min_conf else ("review" if p["confidence"] >= review_conf else "no_match")
        if label in rejected:
            status = "rejected"
        rows.append({**base, "status": status, "eunis_code": e["code"], "eunis_label": e["label"], "eunis_level": e["level"],
                     "match": p["match"], "confidence": f"{p['confidence']:.2f}", "note": p.get("note") or "", "eunis_uri": e["uri"]})
        if status == "linked":
            links[label] = (e["code"], p["match"])

    # apply to the Habitat objects (shared per label)
    canon = {}
    n_obs = 0
    for entry in result.entries:
        for obs in entry.observations:
            h = obs.habitat
            if h is None or h.label not in links:
                continue
            if h.label not in canon:
                code, match = links[h.label]
                e = vocab.rows[code]
                canon[h.label] = replace(h, eunis_code=code, eunis_label=e["label"], eunis_match=match, eunis_uri=e["uri"],
                                         eunis_parents=tuple((a["code"], a["label"], a["uri"]) for a in vocab.ancestors(code)))
            obs.habitat = canon[h.label]
            n_obs += 1
    logger.info("habitats: %d of %d labels linked to EUNIS (%d observations); %d review, %d no_match",
                len(links), len(labels), n_obs, sum(1 for r in rows if r["status"] == "review"),
                sum(1 for r in rows if r["status"] == "no_match"))
    return len(links), rows
