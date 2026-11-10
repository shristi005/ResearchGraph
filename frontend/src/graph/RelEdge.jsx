import { BaseEdge, EdgeLabelRenderer } from "@xyflow/react";
import { REL } from "../constants";

export default function RelEdge({ id, sourceX, sourceY, targetX, targetY, data, selected }) {
  const r = REL[data.type];
  const dx = targetX - sourceX, dy = targetY - sourceY, len = Math.hypot(dx, dy) || 1;
  const off = data.offset || 0;
  const cx = (sourceX + targetX) / 2 + (-dy / len) * off * 2;
  const cy = (sourceY + targetY) / 2 + (dx / len) * off * 2;
  const path = `M${sourceX},${sourceY} Q${cx},${cy} ${targetX},${targetY}`;
  // label position along the curve was chosen by placeLabels() so labels do not pile up
  const u = data.labelT ?? 0.5;
  const spot = { x: (1 - u) ** 2 * sourceX + 2 * (1 - u) * u * cx + u * u * targetX, y: (1 - u) ** 2 * sourceY + 2 * (1 - u) * u * cy + u * u * targetY };
  const mx = spot.x, my = spot.y;
  const label = data.display?.short || r.short;
  return (
    <>
      <BaseEdge id={id} path={path} interactionWidth={22}
        style={{ stroke: r.color, strokeWidth: selected ? 4.5 : 2.6, strokeDasharray: r.dash || undefined, opacity: data.dim ? 0.12 : 0.95, filter: "url(#rough)" }} />
      <EdgeLabelRenderer>
        <button
          className="nodrag nopan absolute cursor-pointer rounded-full border px-1.5 py-px text-[10px] font-semibold leading-tight"
          style={{ transform: `translate(-50%,-50%) translate(${mx}px,${my}px)`, pointerEvents: "all", background: "#F9F6EE", borderColor: r.color, color: "#2b2a26", opacity: data.dim ? 0.2 : 1 }}
          onClick={() => data.onPick(id)}
          title={r.label}
        >
          {data.type === "citation" ? `${label} →` : label}
        </button>
      </EdgeLabelRenderer>
    </>
  );
}
