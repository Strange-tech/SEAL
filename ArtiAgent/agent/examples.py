"""Lightweight curated-example search for the `find_examples` tool.

This is a deliberately small stand-in for Articraft's full `examples.py`
retrieval engine. We keep the parts that matter for recall on our ~94-example
corpus without pulling in a BM25 dependency:

- stopword filtering (query filler words don't pollute scores),
- code-fence identifiers indexed as their own signal (API names like
  ``KnobGeometry`` or ``Workplane`` usually live only inside code blocks),
- a tiny plural/conjugation stem so ``hinges`` matches ``hinge``,
- field weighting so metadata outranks prose, plus a coverage bonus for
  matching more query terms.

The public entry point keeps the same signature the tool layer already calls:
``search_examples(query, *, examples_dir, limit=3) -> str``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_FRONTMATTER_RE = re.compile(r"\A---\n(?P<frontmatter>.*?)\n---\n?(?P<body>.*)\Z", re.DOTALL)
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_CODE_FENCE_RE = re.compile(r"```[^\n]*\n(?P<code>.*?)```", re.DOTALL)
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_CAMEL_CASE_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "into",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
        "without",
    }
)

# Metadata fields dominate; code outranks prose because the whole point of
# `find_examples` is to locate the right SDK API, which lives in the code.
_FIELD_WEIGHTS = {
    "slug": 4.0,
    "title": 3.5,
    "tags": 3.0,
    "description": 1.75,
    "code": 1.25,
    "prose": 0.5,
}

_STRUCTURED_FIELDS = frozenset({"slug", "title", "tags", "description"})


@dataclass(frozen=True)
class ExampleDocument:
    path: Path
    title: str
    description: str
    tags: tuple[str, ...]
    body: str


@dataclass(frozen=True)
class _IndexedExample:
    doc: ExampleDocument
    fields: dict[str, frozenset[str]]


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return normalized.encode("ascii", "ignore").decode("ascii").lower()


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(_normalize(text))


def _dedupe(tokens: list[str]) -> list[str]:
    return list(dict.fromkeys(tokens))


def _stem_variants(token: str) -> list[str]:
    """Return `[token]` plus light plural/conjugation variants.

    Ambiguous suffixes produce every plausible variant (additive), so the
    correct stem is always present: ``hinges`` -> ``hing`` and ``hinge``,
    ``boxes`` -> ``box`` and ``boxe``, ``making`` -> ``mak`` and ``make``.
    Spurious extras are harmless because matching is set-membership and a
    real stem in a high-weight field still dominates.
    """
    variants = [token]

    def add(candidate: str) -> None:
        if candidate and candidate != token and candidate not in variants:
            variants.append(candidate)

    if token.endswith("ies") and len(token) > 5:
        add(token[:-3] + "y")
    elif token.endswith("ing") and len(token) > 5:
        add(token[:-3])
        add(token[:-3] + "e")
    elif token.endswith("ed") and len(token) > 5:
        add(token[:-2])
        add(token[:-2] + "e")
    elif token.endswith("es") and len(token) > 4:
        add(token[:-2])
        add(token[:-1])
    elif token.endswith("s") and len(token) > 4:
        add(token[:-1])
    return variants


def _meaningful_tokens(text: str) -> list[str]:
    return [token for token in _tokens(text) if token not in _STOPWORDS]


def _split_identifier(identifier: str) -> list[str]:
    expanded = _CAMEL_CASE_RE.sub(" ", identifier.replace("_", " ").replace("-", " "))
    return _meaningful_tokens(expanded)


def _code_tokens(body: str) -> list[str]:
    out: list[str] = []
    for match in _CODE_FENCE_RE.finditer(body):
        for identifier in _IDENTIFIER_RE.findall(match.group("code")):
            out.extend(_split_identifier(identifier))
    return out


def _prose_text(body: str) -> str:
    return _CODE_FENCE_RE.sub("\n", body)


def _field_tokens(tokens: list[str]) -> frozenset[str]:
    return frozenset(variant for token in tokens for variant in _stem_variants(token))


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_frontmatter(path: Path) -> ExampleDocument:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = _FRONTMATTER_RE.match(text)

    title = path.stem.replace("_", " ").strip()
    description = ""
    tags: list[str] = []
    body = text

    if match:
        body = match.group("body")
        current_key: str | None = None
        list_values: list[str] = []

        def flush_list() -> None:
            nonlocal current_key, list_values
            if current_key == "tags":
                tags = list(list_values)
            current_key = None
            list_values = []

        for raw_line in match.group("frontmatter").splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            if stripped.startswith("- "):
                if current_key is not None:
                    list_values.append(_unquote(stripped[2:].strip()))
                continue
            flush_list()
            if ":" not in stripped:
                continue
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()
            if not value:
                current_key = key
                list_values = []
                continue
            value = _unquote(value)
            if key == "title":
                title = value
            elif key == "description":
                description = value
            elif key == "tags":
                if value.startswith("[") and value.endswith("]"):
                    inner = value[1:-1].strip()
                    tags = [part.strip() for part in inner.split(",") if part.strip()] if inner else []
                else:
                    tags = [value]
        flush_list()

    return ExampleDocument(path=path, title=title, description=description, tags=tuple(tags), body=body)


@lru_cache(maxsize=4)
def _load_index(examples_dir_key: str) -> tuple[_IndexedExample, ...]:
    examples_dir = Path(examples_dir_key)
    if not examples_dir.is_dir():
        return ()
    indexed: list[_IndexedExample] = []
    for path in sorted(examples_dir.rglob("*.md")):
        doc = _parse_frontmatter(path)
        fields = {
            "slug": _field_tokens(_meaningful_tokens(path.stem.replace("_", " "))),
            "title": _field_tokens(_meaningful_tokens(doc.title)),
            "description": _field_tokens(_meaningful_tokens(doc.description)),
            "tags": _field_tokens(_meaningful_tokens(" ".join(doc.tags))),
            "prose": _field_tokens(_meaningful_tokens(_prose_text(doc.body))),
            "code": _field_tokens(_code_tokens(doc.body)),
        }
        indexed.append(_IndexedExample(doc=doc, fields=fields))
    return tuple(indexed)


def _score(
    indexed: _IndexedExample,
    query_tokens: list[str],
) -> tuple[float, int, frozenset[str]]:
    score = 0.0
    matched_tokens: set[str] = set()
    matched_fields: set[str] = set()
    for token in query_tokens:
        variants = _stem_variants(token)
        for field_name, field_set in indexed.fields.items():
            if any(variant in field_set for variant in variants):
                score += _FIELD_WEIGHTS[field_name]
                matched_tokens.add(token)
                matched_fields.add(field_name)
    coverage = len(matched_tokens) / len(query_tokens)
    score += coverage * coverage * 3.0
    return score, len(matched_tokens), frozenset(matched_fields)


def _is_strong(matched_count: int, matched_fields: frozenset[str]) -> bool:
    return bool(matched_fields & _STRUCTURED_FIELDS) or matched_count >= 2


def search_examples(
    query: str,
    *,
    examples_dir: Path,
    limit: int = 3,
) -> str:
    limit = max(1, min(int(limit), 8))
    query_tokens = _dedupe(_meaningful_tokens(query))
    if not query_tokens:
        return "Error: query must contain at least one searchable word"

    index = _load_index(str(Path(examples_dir).resolve()))
    if not index:
        return f"Error: no curated examples found under {examples_dir}"

    scored: list[tuple[float, int, frozenset[str], _IndexedExample]] = []
    for indexed in index:
        score, matched_count, matched_fields = _score(indexed, query_tokens)
        if matched_count == 0:
            continue
        scored.append((score, matched_count, matched_fields, indexed))

    scored.sort(key=lambda item: (-item[0], item[3].doc.title, item[3].doc.path.as_posix()))

    if not scored:
        return f"No examples matched query {query!r}. Try more general keywords."

    lines: list[str] = []
    for score, matched_count, matched_fields, indexed in scored[:limit]:
        doc = indexed.doc
        relevance = "" if _is_strong(matched_count, matched_fields) else " [weakly relevant]"
        lines.append(f"### {doc.title}{relevance}")
        if doc.description:
            lines.append(doc.description)
        if doc.tags:
            lines.append(f"tags: {', '.join(doc.tags)}")
        lines.append(doc.body.strip())
        lines.append("")

    header = (
        "Curated SDK example matches (adapt against current SDK docs; "
        "do not copy example code mechanically):\n"
    )
    return header + "\n".join(lines).rstrip() + "\n"
