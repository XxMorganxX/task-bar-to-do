"""AI-derived graph enrichment for todos: embedding-based Related:: links and
LLM entity (Person::) links, consumed by the Obsidian exporter.

See tasks/todo-graph-enrichment.md for the design contract.
"""

from .factory import get_graph_enricher
from .types import TodoEnrichment

__all__ = ["get_graph_enricher", "TodoEnrichment"]
