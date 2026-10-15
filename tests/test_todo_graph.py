"""Behavior tests for todo graph enrichment.

Pure logic (relatedness, entity normalization, cache staleness), the local embedding
cache (provider faked), and the enricher orchestration (all deps injected). No network.
"""

from todo_app.todo_graph import entities as ent
from todo_app.todo_graph.canonical import canonical_map, canonicalize_mapping
from todo_app.todo_graph.embeddings import EmbeddingIndex
from todo_app.todo_graph.enricher import GraphEnricher
from todo_app.todo_graph.relatedness import top_related
from todo_app.todo_graph.types import TodoEnrichment


# --------------------------------------------------------------------------
# relatedness.top_related
# --------------------------------------------------------------------------

def test_related_links_are_symmetric_and_threshold_gated():
    vectors = {"a": [1.0, 0.0], "b": [1.0, 0.0], "c": [0.0, 1.0]}
    result = top_related(vectors, max_links=2, min_similarity=0.9)
    assert result["a"] == ["b"]
    assert result["b"] == ["a"]
    assert result["c"] == []  # orthogonal to both → no link


def test_related_excludes_self_and_respects_cap():
    vectors = {k: [1.0, 0.0] for k in ("a", "b", "c", "d")}
    result = top_related(vectors, max_links=2, min_similarity=0.5)
    assert "a" not in result["a"]
    assert len(result["a"]) == 2  # capped even though 3 others match


def test_related_ignores_zero_vectors():
    vectors = {"a": [1.0, 0.0], "z": [0.0, 0.0]}
    result = top_related(vectors, max_links=3, min_similarity=0.0)
    assert result["z"] == []
    assert "z" not in result["a"]


# --------------------------------------------------------------------------
# entity normalization + cache
# --------------------------------------------------------------------------

def test_normalize_entities_dedupes_case_insensitively_and_strips():
    assert ent.normalize_entities(["Bill", "bill", "  Carol ", "", "Bill"]) == ["Bill", "Carol"]


def test_normalize_entities_rejects_non_list():
    assert ent.normalize_entities("Bill") == []


def test_entities_stale_until_cached_then_fresh_until_text_changes():
    todo = {"id": "t1", "title": "Call Bill", "details": "", "source_metadata": {}}
    assert ent.entities_stale(todo) is True

    payload = ent.entities_cache_payload(["Bill"], todo)
    todo["source_metadata"]["graph"] = payload
    assert ent.entities_stale(todo) is False
    assert ent.cached_entities(todo) == ["Bill"]

    todo["title"] = "Call Bob"
    assert ent.entities_stale(todo) is True


def test_heuristic_extractor_returns_empty():
    assert ent.HeuristicEntityExtractor().extract({"title": "Call Bill"}) == []


# --------------------------------------------------------------------------
# entity canonicalization
# --------------------------------------------------------------------------

def test_case_variants_merge_to_one_canonical_form():
    cmap = canonical_map(["ACME", "Acme", "acme"], {})
    assert set(cmap.values()) == {"Acme"}  # mixed-case form wins over all-caps/lower


def test_acronym_with_no_variant_is_left_untouched():
    cmap = canonical_map(["AWS", "AWS", "Acme"], {})
    assert cmap["AWS"] == "AWS"


def test_explicit_alias_forces_a_merge():
    aliases = {"jane doe startup club": "Jane Doe", "jd": "Jane Doe"}
    cmap = canonical_map(["Jane Doe Startup Club", "JD", "Jane Doe"], aliases)
    assert set(cmap.values()) == {"Jane Doe"}


def test_canonicalize_mapping_consolidates_across_todos_and_dedupes():
    by_id = {"a": ["ACME", "Erin"], "b": ["Acme"], "c": ["acme", "Acme"]}
    out = canonicalize_mapping(by_id, {})
    assert out["a"] == ["Acme", "Erin"]
    assert out["b"] == ["Acme"]
    assert out["c"] == ["Acme"]  # deduped after canonicalization


# --------------------------------------------------------------------------
# EmbeddingIndex — local hash cache (provider faked)
# --------------------------------------------------------------------------

class _FakeProvider:
    def __init__(self):
        self.batch_calls = 0

    async def initialize(self):
        return True

    async def embed_batch(self, texts):
        self.batch_calls += 1
        return [[float(len(t)), 1.0] for t in texts]


def test_embedding_index_caches_and_skips_reembedding(tmp_path):
    provider = _FakeProvider()
    items = [("a", "alpha", "h1"), ("b", "beta", "h2")]
    index = EmbeddingIndex(tmp_path / "vec.json", provider=provider)

    vectors = index.vectors_for(items)
    assert set(vectors) == {"a", "b"}
    assert provider.batch_calls == 1

    # A fresh index loads the cache file → no re-embedding for the same hashes.
    provider2 = _FakeProvider()
    index2 = EmbeddingIndex(tmp_path / "vec.json", provider=provider2)
    index2.vectors_for(items)
    assert provider2.batch_calls == 0


def test_embedding_index_prunes_stale_hashes(tmp_path):
    provider = _FakeProvider()
    index = EmbeddingIndex(tmp_path / "vec.json", provider=provider)
    index.vectors_for([("a", "alpha", "h1"), ("b", "beta", "h2")])

    # Re-run with only one item → the other hash is pruned from the cache file.
    index.vectors_for([("a", "alpha", "h1")])
    import json
    cached = json.loads((tmp_path / "vec.json").read_text())
    assert set(cached) == {"h1"}


# --------------------------------------------------------------------------
# GraphEnricher orchestration (deps injected)
# --------------------------------------------------------------------------

class _FakeExtractor:
    name = "fake"

    def extract(self, todo):
        return ["Bill"] if "Bill" in (todo.get("title") or "") else []


class _FakeWriter:
    def __init__(self):
        self.calls = []

    def update_todo_metadata(self, *, user, todo_id, metadata_updates, merge=True):
        self.calls.append((todo_id, metadata_updates))
        return {"success": True}


class _FakeIndex:
    def vectors_for(self, items):
        # Make a and b identical, c orthogonal.
        table = {"a": [1.0, 0.0], "b": [1.0, 0.0], "c": [0.0, 1.0]}
        return {i: table[i] for (i, _t, _h) in items if i in table}


def test_enricher_returns_entities_and_related_and_persists_entities():
    writer = _FakeWriter()
    enricher = GraphEnricher(
        extractor=_FakeExtractor(),
        metadata_writer=writer,
        embedding_index_factory=lambda user: _FakeIndex(),
    )
    todos = [
        {"id": "a", "title": "Call Bill", "details": "x", "source_metadata": {}},
        {"id": "b", "title": "Email Bill", "details": "y", "source_metadata": {}},
        {"id": "c", "title": "Buy milk", "details": "z", "source_metadata": {}},
    ]

    result = enricher.enrich(user="Alice", todos=todos)

    assert isinstance(result["a"], TodoEnrichment)
    assert result["a"].entities == ["Bill"]
    assert result["c"].entities == []
    assert result["a"].related_ids == ["b"]  # identical vectors
    assert result["c"].related_ids == []     # orthogonal
    # Entities were cached back through the writer (extractor is not heuristic).
    assert any(todo_id == "a" for todo_id, _ in writer.calls)
