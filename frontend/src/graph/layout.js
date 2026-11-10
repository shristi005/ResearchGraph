/** Deterministic force-directed layout, computed once per dataset (no extra dependency).
 *  Nodes are wide cards (~230x100), so distances are measured on a stretched y-axis and a final
 *  pass pushes apart any rectangles that still overlap. */
const NODE_W = 250, NODE_H = 120;

export function forceLayout(nodes, edges) {
  const n = nodes.length;
  if (!n) return {};
  const W = 700 + n * 150, H = 480 + n * 90;
  const pos = nodes.map((_, i) => ({
    x: W / 2 + Math.cos((2 * Math.PI * i) / n) * (W / 2.6),
    y: H / 2 + Math.sin((2 * Math.PI * i) / n) * (H / 2.6),
    vx: 0, vy: 0,
  }));
  const idx = Object.fromEntries(nodes.map((nd, i) => [nd.id, i]));
  const pairs = [...new Set(edges.map((e) => [e.source, e.target].sort().join("|")))].map((k) => k.split("|"));

  for (let it = 0; it < 400; it++) {
    const cool = 1 - it / 400;
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      const dx = pos[i].x - pos[j].x, dy = (pos[i].y - pos[j].y) * 1.9;
      const d2 = Math.max(dx * dx + dy * dy, 900), d = Math.sqrt(d2), f = 190000 / d2;
      pos[i].vx += (dx / d) * f; pos[i].vy += (dy / d / 1.9) * f;
      pos[j].vx -= (dx / d) * f; pos[j].vy -= (dy / d / 1.9) * f;
    }
    for (const [a, b] of pairs) {
      const i = idx[a], j = idx[b];
      if (i === undefined || j === undefined) continue;
      const dx = pos[j].x - pos[i].x, dy = pos[j].y - pos[i].y, d = Math.max(Math.hypot(dx, dy), 1);
      const f = (d - 380) * 0.008;
      pos[i].vx += (dx / d) * f; pos[i].vy += (dy / d) * f;
      pos[j].vx -= (dx / d) * f; pos[j].vy -= (dy / d) * f;
    }
    for (const p of pos) {
      p.vx += (W / 2 - p.x) * 0.002; p.vy += (H / 2 - p.y) * 0.002;
      p.x += Math.max(-45, Math.min(45, p.vx)) * cool; p.y += Math.max(-45, Math.min(45, p.vy)) * cool;
      p.vx *= 0.55; p.vy *= 0.55;
    }
  }

  // overlap removal: push apart cards whose rectangles (plus a gap) still intersect
  const gapX = 50, gapY = 50;
  for (let pass = 0; pass < 120; pass++) {
    let moved = false;
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      const dx = pos[j].x - pos[i].x, dy = pos[j].y - pos[i].y;
      const ox = NODE_W + gapX - Math.abs(dx), oy = NODE_H + gapY - Math.abs(dy);
      if (ox > 0 && oy > 0) {
        moved = true;
        if (ox < oy) { const s = (dx >= 0 ? 1 : -1) * ox / 2; pos[i].x -= s; pos[j].x += s; }
        else { const s = (dy >= 0 ? 1 : -1) * oy / 2; pos[i].y -= s; pos[j].y += s; }
      }
    }
    if (!moved) break;
  }
  return Object.fromEntries(nodes.map((nd, i) => [nd.id, { x: pos[i].x, y: pos[i].y }]));
}
