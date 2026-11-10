import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ExternalLink, FileText, RefreshCw, Sparkles } from "lucide-react";
import { api, errMsg, openPaperPdf } from "../api";
import { Button, Card, Chip, ErrorBox, SourceBadge, Spinner, StatusPill, StepTracker, Term } from "../components/ui";

const List = ({ items, empty = "Not stated in the paper.", pages = {} }) =>
  items?.length ? <ul className="list-disc space-y-1 pl-5 text-sm">{items.map((x, i) => <li key={i}>{x}{pages[x] ? <span className="ml-1 text-xs text-forest">(p. {pages[x]})</span> : null}{pages[x] === undefined && x in pages ? null : null}</li>)}</ul> : <p className="text-sm italic text-ink/50">{empty}</p>;

const Section = ({ title, color, children, delay = 0 }) => (
  <Card className="rise" style={{ animationDelay: `${delay}s` }}>
    <h3 className="mb-2 flex items-center gap-2 font-hand text-2xl font-bold"><span className="h-3 w-3 rounded-full border border-ink/50" style={{ background: color }} />{title}</h3>
    {children}
  </Card>
);

export default function PaperAnalysis() {
  const { id } = useParams();
  const [paper, setPaper] = useState(null);
  const [res, setRes] = useState(null);
  const [error, setError] = useState("");
  const [text, setText] = useState(null);
  const [tick, setTick] = useState(0);
  const timer = useRef(null);

  const load = useCallback(async () => {
    try {
      const [p, a] = await Promise.all([api.get(`/api/papers/${id}`), api.get(`/api/papers/${id}/analysis`)]);
      setPaper(p.data); setRes(a.data); setError("");
      clearTimeout(timer.current);
      if (a.data.status === "analyzing") timer.current = setTimeout(load, 2000);
    } catch (e) { setError(errMsg(e)); }
  }, [id]);

  useEffect(() => { load(); return () => clearTimeout(timer.current); }, [load]);
  useEffect(() => { const t = setInterval(() => setTick((x) => x + 1), 4000); return () => clearInterval(t); }, []);

  const reread = async () => {
    try { await api.post(`/api/papers/${id}/reprocess`); await load(); } catch (e) { setError(errMsg(e)); }
  };
  const analyze = async () => {
    try { await api.post(`/api/papers/${id}/analyze`); await load(); } catch (e) { setError(errMsg(e)); }
  };
  const showText = async () => {
    if (text !== null) return setText(null);
    try { setText((await api.get(`/api/papers/${id}/text`)).data.text); } catch (e) { setError(errMsg(e)); }
  };

  if (!paper && !error) return <Spinner label="Loading paper…" />;
  if (!paper) return <ErrorBox>{error}</ErrorBox>;
  const a = res?.analysis;
  const pageOf = (field) => Object.fromEntries((a?.evidence || []).filter((e) => e.field === field && e.verified && e.page).map((e) => [e.item, e.page]));
  const analyzing = res?.status === "analyzing";

  return (
    <div className="mx-auto max-w-4xl">
      <Link to="/papers" className="mb-3 inline-flex items-center gap-1 text-sm text-forest hover:underline"><ArrowLeft size={14} /> My Papers</Link>
      <div className="rise mb-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h1 className="font-display text-3xl font-semibold leading-tight">{paper.title}</h1>
          <StatusPill status={paper.status} />
        </div>
        <p className="mt-1 text-sm text-ink/70">
          {a?.authors?.length ? a.authors.join(", ") : paper.pdf_author ? `${paper.pdf_author} (PDF metadata)` : "Authors not detected"}
          {a?.publication_year ? ` · ${a.publication_year}` : ""} · {paper.page_count} pages · {paper.original_filename}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button onClick={analyze} loading={analyzing} variant={a ? "ghost" : "primary"}>{a ? <RefreshCw size={15} /> : <Sparkles size={15} />}{analyzing ? "Analyzing…" : a ? "Analyze again" : "Analyze paper"}</Button>
          <Button variant="ghost" onClick={() => openPaperPdf(id).catch((e) => setError(errMsg(e)))}><ExternalLink size={15} /> Open original PDF</Button>
          <Button variant="ghost" onClick={reread} title="Re-read the original PDF with the layout-aware extractor. No AI is used and your analysis is kept."><RefreshCw size={15} /> Re-read PDF (no AI)</Button>
          <Button variant="ghost" onClick={showText}><FileText size={15} /> {text !== null ? "Hide" : "Show"} extracted text</Button>
        </div>
      </div>

      <ErrorBox className="mb-4">{error || res?.error}</ErrorBox>

      {analyzing && (
        <Card className="mb-5 py-8">
          <p className="mb-4 text-center font-display text-xl">Analyzing this paper…</p>
          <StepTracker steps={["Finding sections", "Asking the model", "Checking the result"]} active={tick % 3} />
          <p className="mt-4 text-center text-xs text-ink/60">Small local models can take a minute or two per paper. You can leave this page; progress is saved.</p>
        </Card>
      )}

      {text !== null && (
        <Card soft className="mb-5"><pre className="max-h-96 overflow-auto whitespace-pre-wrap text-xs leading-relaxed">{text}</pre></Card>
      )}

      {!a && !analyzing && <Card soft className="text-center"><p className="font-hand text-3xl text-forest">Not analyzed yet</p><p className="text-sm text-ink/70">Press “Analyze paper” to extract topics, methods, findings and limitations.</p></Card>}

      {a && (
        <div className="space-y-4">
          {a.warnings.length > 0 && (
            <Card soft className="!bg-[#fbf0dc]"><p className="font-semibold text-sm">Checks applied to the AI output</p><List items={a.warnings} /></Card>
          )}
          <div className="flex flex-wrap items-center gap-2 text-sm">
            {a.article_type && <Chip color="#D9C5A8"><Term hint={a.article_type_reason || "Detected from the section structure"}>Article type: {a.article_type}</Term></Chip>}
            <Chip color="#EFE3D1"><Term hint="How well the expected sections were found and how many extracted statements could be matched to a sentence in the PDF (0 to 1)">Extraction confidence: {a.extraction_confidence ?? "n/a"}</Term></Chip>
          </div>
          <Section title="Abstract" color="#EFE3D1">
            {a.abstract ? <><p className="text-sm leading-relaxed">{a.abstract}</p>
              <p className="mt-1 text-xs text-ink/55">Copied word for word from page {a.abstract_page ?? "?"}{a.abstract_source === "inferred" ? ". The PDF has no Abstract heading, so this is the first long paragraph of the front matter. Please check it." : "."}</p></>
              : <p className="text-sm italic text-ink/50">No abstract found. See “Section detection” below for why.</p>}
          </Section>
          <div className="grid gap-4 md:grid-cols-2">
            <Section title="Research problem" color="#D9A566" delay={0.05}>{a.research_problem ? <p className="text-sm">{a.research_problem}</p> : <p className="text-sm italic text-ink/50">Not stated.</p>}</Section>
            <Section title="Objectives" color="#D9A566" delay={0.1}><List items={a.objectives} /></Section>
            <Section title="Topics & keywords" color="#A8C3B0" delay={0.15}>
              <div className="flex flex-wrap gap-1.5">{[...a.topics.map((t) => [t, "#A8C3B0"]), ...a.keywords.map((t) => [t, "#EFE3D1"])].map(([t, c], i) => <Chip key={i} color={c}>{t}</Chip>)}</div>
              {!a.topics.length && !a.keywords.length && <p className="text-sm italic text-ink/50">None extracted.</p>}
            </Section>
            <Section title="Methods & algorithms" color="#B06A4F" delay={0.2}>
              <div className="flex flex-wrap gap-1.5">{[...a.methodologies, ...a.algorithms].map((t, i) => <Chip key={i} color="#E5B5A5">{t}</Chip>)}</div>
              {!a.methodologies.length && !a.algorithms.length && <p className="text-sm italic text-ink/50">None extracted.</p>}
            </Section>
            <Section title="Findings" color="#3F5D4E" delay={0.25}><List items={a.findings} pages={pageOf("findings")} /></Section>
            <Section title="Limitations" color="#6B7B8B" delay={0.3}><List items={a.limitations} pages={pageOf("limitations")} empty="No limitations explicitly stated." /></Section>
          </div>
          <Section title="Future work" color="#D9C5A8" delay={0.35}><List items={a.future_work} pages={pageOf("future_work")} empty="No future work explicitly stated." /></Section>
          <Card soft>
            <details>
              <summary className="cursor-pointer font-semibold">Section detection<SourceBadge kind="pdf" /></summary>
              <ul className="mt-2 space-y-1 text-sm">
                {a.section_report.map((r) => (
                  <li key={r.section} className="flex flex-wrap gap-x-2">
                    <span className={`w-28 shrink-0 font-semibold ${r.found ? "text-forest" : "text-ink/50"}`}>{r.found ? "✓" : "–"} {r.section.replaceAll("_", " ")}</span>
                    <span className="text-ink/70">{r.found ? `${r.method === "inferred" ? "inferred" : "found"}${r.page ? `, page ${r.page}` : ""}` : "not found"}{r.reason ? `. ${r.reason}` : ""}</span>
                  </li>
                ))}
                {!a.section_report.length && <li className="italic text-ink/50">Press “Re-read PDF (no AI)” to compute this for an older analysis.</li>}
              </ul>
            </details>
          </Card>
          <p className="text-xs text-ink/50">Sections read by the model: {a.sections_used.join(", ")}. AI output may contain mistakes; check it against the PDF.</p>
        </div>
      )}
    </div>
  );
}
