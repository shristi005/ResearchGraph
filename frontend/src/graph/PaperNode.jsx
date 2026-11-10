import { Handle, Position } from "@xyflow/react";
import { Share2 } from "lucide-react";

const hidden = { opacity: 0, left: "50%", top: "50%", pointerEvents: "none" };

export default function PaperNode({ data, selected }) {
  return (
    <div
      className={`sketch w-[230px] px-3.5 py-3 transition ${selected ? "!bg-mustard/60" : data.match ? "!bg-sage/60" : "!bg-sage/30"}`}
      style={{ opacity: data.dim ? 0.28 : 1, transform: selected ? "scale(1.04)" : undefined }}
    >
      <Handle type="target" position={Position.Top} style={hidden} isConnectable={false} />
      <Handle type="source" position={Position.Top} style={hidden} isConnectable={false} />
      <p className="line-clamp-3 font-display text-[15px] font-semibold leading-snug" title={data.title}>{data.title}</p>
      <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px]">
        {data.year && <span className="rounded-full border border-ink/30 bg-ivory px-2 py-0.5 font-semibold">{data.year}</span>}
        {data.main_topic && <span className="max-w-[130px] truncate rounded-full border border-ink/30 bg-beige px-2 py-0.5" title={data.main_topic}>{data.main_topic}</span>}
        <span className="ml-auto flex items-center gap-1 font-semibold" title="Number of connected papers"><Share2 size={12} />{data.connections}</span>
      </div>
    </div>
  );
}
