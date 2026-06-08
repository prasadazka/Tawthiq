"""Re-usable loader for the Saudi IFRS taxonomy mapping.

Load the YAML once, then look up by business_term, synonym, or XBRL tag.
Used by:
  - AI mapping prompts (to give the model the canonical concept list)
  - XBRL generator (to translate matched line items into XBRL elements)
  - Validation (to spot when an extracted concept has no taxonomy entry)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterator

import yaml

DEFAULT_MAPPING_PATH = Path(__file__).parent / "taxonomy_mapping.yml"

# Tags that aren't real XBRL elements — they describe what XBRL artifact the
# extractor should produce (a context, a unit, or a yet-to-be-defined local
# extension).
NON_TAG_VALUES = {"Context", "Unit", "Local Extension"}


@dataclass
class Concept:
    """One taxonomy entry — a business term mapped to an XBRL element (or a
    semantic marker like Context / Unit / Local Extension)."""
    business_term: str
    xbrl_tag: str
    section_id: str
    section_title: str
    synonyms: list[str] = field(default_factory=list)

    @property
    def is_real_tag(self) -> bool:
        return self.xbrl_tag not in NON_TAG_VALUES

    @property
    def namespace_prefix(self) -> str | None:
        if not self.is_real_tag or ":" not in self.xbrl_tag:
            return None
        return self.xbrl_tag.split(":", 1)[0]

    @property
    def local_name(self) -> str | None:
        if not self.is_real_tag or ":" not in self.xbrl_tag:
            return None
        return self.xbrl_tag.split(":", 1)[1]

    def all_labels(self) -> list[str]:
        """Canonical business term + every synonym."""
        return [self.business_term, *self.synonyms]


@dataclass
class Section:
    id: str
    title: str
    concepts: list[Concept]
    namespace: str | None = None


@dataclass
class Taxonomy:
    metadata: dict
    namespaces: dict[str, str]
    sections: list[Section]
    _by_term: dict[str, Concept]
    _by_tag: dict[str, Concept]

    # ── public lookup API ──────────────────────────────────────────────────

    def concept_for_term(self, label: str) -> Concept | None:
        """Match a label (business_term OR synonym), case-insensitive, trimmed."""
        if not label:
            return None
        return self._by_term.get(_normalize(label))

    def concept_for_tag(self, xbrl_tag: str) -> Concept | None:
        if not xbrl_tag:
            return None
        return self._by_tag.get(xbrl_tag.strip())

    def all_concepts(self) -> Iterator[Concept]:
        for section in self.sections:
            yield from section.concepts

    def real_concepts(self) -> Iterator[Concept]:
        return (c for c in self.all_concepts() if c.is_real_tag)

    def section(self, section_id: str) -> Section | None:
        return next((s for s in self.sections if s.id == section_id), None)

    @property
    def concept_count(self) -> int:
        return sum(1 for _ in self.all_concepts())

    @property
    def synonym_count(self) -> int:
        return sum(len(c.synonyms) for c in self.all_concepts())


def _normalize(label: str) -> str:
    return " ".join(label.strip().lower().split())


def load_taxonomy(path: str | Path | None = None) -> Taxonomy:
    """Load and index the taxonomy. Fails loudly on malformed YAML."""
    p = Path(path) if path else DEFAULT_MAPPING_PATH
    with open(p, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)

    sections: list[Section] = []
    by_term: dict[str, Concept] = {}
    by_tag: dict[str, Concept] = {}
    duplicate_terms: list[str] = []

    for raw_section in doc.get("sections", []):
        section = Section(
            id=raw_section["id"],
            title=raw_section.get("title", raw_section["id"]),
            namespace=raw_section.get("namespace"),
            concepts=[],
        )
        for raw_concept in raw_section.get("concepts", []):
            concept = Concept(
                business_term=raw_concept["business_term"],
                xbrl_tag=raw_concept["xbrl_tag"],
                section_id=section.id,
                section_title=section.title,
                synonyms=list(raw_concept.get("synonyms") or []),
            )
            section.concepts.append(concept)

            for label in concept.all_labels():
                key = _normalize(label)
                if key in by_term and by_term[key] is not concept:
                    duplicate_terms.append(label)
                else:
                    by_term[key] = concept

            # Index by tag only for real tags (Context/Unit/Local Extension
            # can repeat across many concepts).
            if concept.is_real_tag:
                # Multiple concepts can share a real tag too (e.g. "Total
                # Equity" + "Closing Equity" both map to ifrs-full:Equity);
                # keep the first occurrence so lookup is stable.
                by_tag.setdefault(concept.xbrl_tag, concept)

        sections.append(section)

    if duplicate_terms:
        raise ValueError(
            "Duplicate business_term or synonym across concepts: "
            + ", ".join(sorted(set(duplicate_terms)))
        )

    return Taxonomy(
        metadata=doc.get("metadata", {}),
        namespaces=doc.get("namespaces", {}),
        sections=sections,
        _by_term=by_term,
        _by_tag=by_tag,
    )


@lru_cache(maxsize=1)
def default_taxonomy() -> Taxonomy:
    """Module-level cached taxonomy — call this from anywhere."""
    return load_taxonomy()
