def pick(ranked: list[tuple[int, int, float]], paper_ids: list[int], k: int) -> list[int]:
    """ranked = [(chunk_id, paper_id, similarity)] best first. Returns chunk ids: best overall, but when few papers are
    selected each selected paper keeps its single best chunk, so no paper is crowded out of the answer."""
    picked: list[int] = []
    if len(paper_ids) <= k // 2 + 1:
        for pid in paper_ids:
            best = next((cid for cid, p, _ in ranked if p == pid), None)
            if best is not None and best not in picked:
                picked.append(best)
    for cid, _, _ in ranked:
        if len(picked) >= k:
            break
        if cid not in picked:
            picked.append(cid)
    sim = {cid: s for cid, _, s in ranked}
    return sorted(picked, key=lambda c: -sim[c])[:k]
