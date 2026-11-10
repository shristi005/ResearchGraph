import { Link } from "react-router-dom";
import { Eye, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import { Button, Card, Chip, StatusPill } from "./ui";

export default function PaperCard({ paper: p, onAnalyze, onDelete, busy, index = 0 }) {
  const analyzed = p.has_extraction;
  return (
    <Card className="rise sketch-hover flex min-w-0 flex-col gap-2" style={{ animationDelay: `${Math.min(index, 8) * 0.06}s` }}>
      <div className="flex items-start justify-between gap-2">
        <Link to={`/papers/${p.id}`} className="font-display text-lg font-semibold leading-snug hover:text-forest">{p.title}</Link>
        <StatusPill status={p.status} />
      </div>
      <p className="truncate text-xs text-ink/60" title={p.original_filename}>
        {p.original_filename} · {p.page_count} pages · {(p.size_bytes / 1024).toFixed(0)} KB
        {p.publication_year ? ` · ${p.publication_year}` : ""}
      </p>
      {p.title_source !== "analysis" && (
        <p className="text-xs italic text-ink/55">
          {p.title_source === "pdf_metadata" ? "Title from PDF metadata (not yet analyzed)." : "No title detected yet. Showing file name."}
        </p>
      )}
      {p.topics.length > 0 && <div className="flex flex-wrap gap-1.5">{p.topics.slice(0, 4).map((t) => <Chip key={t} color="#A8C3B0">{t}</Chip>)}</div>}
      {p.error && <p className="rounded-lg bg-[#f6e3da] p-2 text-xs text-terracotta">{p.error}</p>}
      <div className="mt-auto flex flex-wrap items-center gap-2 pt-2">
        <Button variant={analyzed ? "ghost" : "primary"} onClick={() => onAnalyze(p.id)} loading={busy || p.status === "analyzing"} className="!px-3 !py-1.5">
          {analyzed ? <RefreshCw size={14} /> : <Sparkles size={14} />}
          {p.status === "analyzing" ? "Analyzing…" : analyzed ? "Re-analyze" : "Analyze paper"}
        </Button>
        <Link to={`/papers/${p.id}`}><Button variant="ghost" className="!px-3 !py-1.5"><Eye size={14} /> Details</Button></Link>
        <Button variant="danger" onClick={() => onDelete(p)} className="ml-auto !px-2.5 !py-1.5" aria-label={`Delete ${p.title}`}><Trash2 size={14} /></Button>
      </div>
    </Card>
  );
}
