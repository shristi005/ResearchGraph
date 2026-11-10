import { useState } from "react";
import { Sparkles } from "lucide-react";
import { api, errMsg } from "../api";
import PaperCard from "../components/PaperCard";
import UploadZone from "../components/UploadZone";
import { Button, Card, EmptyState, ErrorBox, PageHeader, Spinner } from "../components/ui";
import { usePapers } from "../usePapers";

export default function Papers() {
  const { papers, loading, error, refresh } = usePapers();
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);

  const analyze = async (id) => {
    setActionError("");
    try {
      await api.post(`/api/papers/${id}/analyze`);
      await refresh();
    } catch (e) {
      setActionError(errMsg(e));
    }
  };
  const analyzeAll = async () => {
    setBusy(true); setActionError("");
    try {
      for (const p of papers.filter((x) => !x.has_extraction && x.status !== "analyzing")) await api.post(`/api/papers/${p.id}/analyze`);
      await refresh();
    } catch (e) {
      setActionError(errMsg(e));
    } finally {
      setBusy(false);
    }
  };
  const remove = async (p) => {
    if (!window.confirm(`Delete "${p.title}"? This removes the PDF, its analysis and its graph connections.`)) return;
    try { await api.delete(`/api/papers/${p.id}`); await refresh(); } catch (e) { setActionError(errMsg(e)); }
  };

  const pending = papers.filter((p) => !p.has_extraction && p.status !== "analyzing").length;
  const running = papers.filter((p) => p.status === "analyzing").length;

  return (
    <div>
      <PageHeader title="My Papers" subtitle="Upload research PDFs, then let AI read them. Analysis runs one paper at a time, so a batch can take a few minutes.">
        {pending > 0 && <Button onClick={analyzeAll} loading={busy}><Sparkles size={15} /> Analyze all ({pending})</Button>}
      </PageHeader>
      <Card className="mb-6"><UploadZone onUploaded={refresh} /></Card>
      <ErrorBox className="mb-4">{error || actionError}</ErrorBox>
      {running > 0 && <p className="mb-3 font-hand text-2xl text-forest">Reading {running} paper{running > 1 ? "s" : ""}… this page updates by itself.</p>}
      {loading ? <Spinner label="Loading papers…" /> : papers.length === 0 ? (
        <EmptyState title="No papers yet">Drop a few PDFs above to get started. Try the files in the <code>sample_papers</code> folder.</EmptyState>
      ) : (
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
          {papers.map((p, i) => <PaperCard key={p.id} paper={p} index={i} onAnalyze={analyze} onDelete={remove} />)}
        </div>
      )}
    </div>
  );
}
