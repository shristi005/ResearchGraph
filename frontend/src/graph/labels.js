/** Greedy label placement: choose, for every edge, the point along its curve (parameter t) where the label
 *  overlaps the fewest other labels and paper cards. Node positions are static, so this is computed once. */
const NODE_HALF_W = 115, NODE_HALF_H = 52;

export function placeLabels(nodes, edges, positions) {
  const center = (id) => ({ x: (positions[id]?.x ?? 0) + NODE_HALF_W, y: (positions[id]?.y ?? 0) + NODE_HALF_H });
  const cards = nodes.map((n) => center(n.id));
  const placed = [];
  const out = {};
  const TS = [0.5, 0.42, 0.58, 0.34, 0.66, 0.27, 0.73, 0.2, 0.8, 0.14, 0.86, 0.46, 0.54, 0.38, 0.62];
  for (const e of [...edges].sort((a, b) => (a.id < b.id ? -1 : 1))) {
    const s = center(e.source), t = center(e.target);
    const dx = t.x - s.x, dy = t.y - s.y, len = Math.hypot(dx, dy) || 1;
    const cx = (s.x + t.x) / 2 + (-dy / len) * (e.offset || 0) * 2, cy = (s.y + t.y) / 2 + (dx / len) * (e.offset || 0) * 2;
    const w = Math.max(60, (e.text?.length || 8) * 6 + 18), h = 20;
    let best = null;
    for (const u of TS) {
      const p = { x: (1 - u) ** 2 * s.x + 2 * (1 - u) * u * cx + u * u * t.x, y: (1 - u) ** 2 * s.y + 2 * (1 - u) * u * cy + u * u * t.y };
      let penalty = 0;
      for (const q of placed) if (Math.abs(p.x - q.x) < (w + q.w) / 2 + 3 && Math.abs(p.y - q.y) < h + 2) penalty += 100;
      for (const c of cards) if (Math.abs(p.x - c.x) < NODE_HALF_W + w / 2 && Math.abs(p.y - c.y) < NODE_HALF_H + h / 2) penalty += 12;
      if (best === null || penalty < best.penalty) best = { u, p, penalty };
      if (penalty === 0) break;
    }
    out[e.id] = best.u;
    placed.push({ ...best.p, w });
  }
  return out;
}
