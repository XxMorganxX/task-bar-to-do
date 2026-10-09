"""Pure cosine-similarity nearest-neighbours over a set of todo vectors.

No I/O. Given id -> embedding, return id -> the most similar other ids above a
threshold, capped and sorted by similarity. Symmetric inputs give symmetric pairs.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Sequence

import numpy as np


def top_related(
    vectors: Mapping[str, Sequence[float]],
    *,
    max_links: int,
    min_similarity: float,
) -> Dict[str, List[str]]:
    """For each id, the up-to-`max_links` other ids with cosine >= `min_similarity`,
    highest first. Self is always excluded; zero vectors relate to nothing."""
    ids = [i for i, v in vectors.items() if v is not None and len(v) > 0]
    if len(ids) < 2 or max_links <= 0:
        return {i: [] for i in vectors}

    matrix = np.array([vectors[i] for i in ids], dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    safe = norms.copy()
    safe[safe == 0] = 1.0
    unit = matrix / safe
    sims = unit @ unit.T  # (N, N) cosine similarities

    result: Dict[str, List[str]] = {i: [] for i in vectors}
    for row, source_id in enumerate(ids):
        if norms[row][0] == 0:
            continue
        # Candidate (similarity, id) pairs excluding self and zero-norm rows.
        candidates = [
            (float(sims[row][col]), ids[col])
            for col in range(len(ids))
            if col != row and norms[col][0] != 0
        ]
        candidates.sort(key=lambda pair: (-pair[0], pair[1]))
        result[source_id] = [
            other for score, other in candidates[:max_links] if score >= min_similarity
        ]
    return result


__all__ = ["top_related"]
