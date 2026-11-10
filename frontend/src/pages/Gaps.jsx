import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Check, GraduationCap, HelpCircle, Lightbulb, Loader2, ShieldAlert, Wand2, X } from "lucide-react";
import { api, errMsg } from "../api";
import { CATEGORY } from "../constants";
import { Block, Bullets, Button, Card, Chip, EmptyState, ErrorBox, PageHeader, Quote, SourceBadge, Spinner, Term } from "../components/ui";

const REVIEW = [
  { v: "accepted", label: "Accept", icon: Check, bg: "#A8C3B0" },
  { v: "needs_investigation", label: "Needs investigation", icon: HelpCircle, bg: "#D9A566" },
  { v: "rejected", label: "Reject", icon: X, bg: "#E5B5A5" },
];
const TONE = { accepted: "#e6efe9", rejected: "#f6e3da", needs_investigation: "#fbf0dc", new: "#F9F6EE" };

function Feasibility({ h, onDone }) {
  const [ctx, setCtx] = useState({ compute: "", experience: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const f = h.feasibility;
  const run = async (refresh = false) => {
    setBusy(true); setErr("");
    try { await api.post(`/api/gaps/${h.id}/feasibility`, ctx, { params: refresh ? { refresh: true } : {} }); await onDone(); }
    catch (e) { setErr(errMsg(e)); } finally { setBusy(false); }
  };
  const a = f?.analysis;
  return (
    <details className="rounded-xl border-2 border-ink/25 bg-ivory/70 p-3">
      <summary className="cursor-pointer font-semibold">Student feasibility analysis{a && <SourceBadge kind="ai" />}</summary>
      <div className="mt-3 space-y-2">
        <div className="grid gap-2 md:grid-cols-2">
          <input className="rounded-lg border border-ink/30 bg-ivory px-3 py-1.5 text-sm" placeholder="Your computing (e.g. laptop, CPU only)" value={ctx.compute} onChange={(e) => setCtx({ ...ctx, compute: e.target.value })} aria-label="Your computing resources" />
          <input className="rounded-lg border border-ink/30 bg-ivory px-3 py-1.5 text-sm" placeholder="Your background (e.g. final-year, Python)" value={ctx.experience} onChange={(e) => setCtx({ ...ctx, experience: e.target.value })} aria-label="Your background" />
        </div>
        <Button onClick={() => run(!!a)} loading={busy} className="!py-1.5">{a ? "Re-analyze" : "Analyze feasibility"}</Button>
        <ErrorBox>{err}</ErrorBox>
        {f?.error && <ErrorBox>The AI analysis is unavailable: {f.error}</ErrorBox>}
        {a && (
          <div className="grid gap-x-6 md:grid-cols-2">
            <Block title="Implementation complexity"><p>{a.complexity}</p></Block>
            <Block title="Suitable for an undergraduate project?"><p>{a.undergraduate_suitability}</p></Block>
            <Block title="Technical knowledge needed"><Bullets items={a.technical_knowledge} /></Block>
            <Block title="Tools and technologies"><Bullets items={a.tools} /></Block>
            <Block title="Dataset availability"><p>{a.dataset_availability}</p></Block>
            <Block title="Computing requirements"><p>{a.computing_requirements}</p></Block>
            <Block title="Suggested implementation approach"><ol className="list-decimal space-y-1 pl-5">{a.implementation_approach.map((x, i) => <li key={i}>{x}</li>)}</ol></Block>
            <Block title="Expected challenges"><Bullets items={a.challenges} /></Block>
            <Block title="Possible evaluation metrics"><Bullets items={a.evaluation_metrics} /></Block>
          </div>
        )}
        {f?.manual_validation && (
          <div className="rounded-lg border border-terracotta/50 bg-[#f6e3da] p-2 text-xs">
            <b>Needs manual validation:</b>
            <ul className="list-disc pl-5">{f.manual_validation.map((m, i) => <li key={i}>{m}</li>)}</ul>
          </div>
        )}
      </div>
    </details>
  );
}

function OpportunityCard({ h, titles, onReview, onChanged, index }) {
  const cat = CATEGORY[h.category] || { label: h.category, color: "#EFE3D1" };
  const writing = h.enrichment_status === "pending";
  return (
    <Card className="rise space-y-3" style={{ background: TONE[h.review_status], animationDelay: `${Math.min(index, 8) * 0.06}s` }}>
      <div className="flex flex-wrap items-center gap-2">
        <Chip color={cat.color}>{cat.label}</Chip>
        <Chip color="#EFE3D1"><Term hint={`Score ${h.confidence_score ?? "n/a"} out of 1, computed from the evidence: number of supporting papers, wording agreement, quote sources, extraction quality. 'High' is never offered because nothing here is verified.`}>Confidence: {h.confidence}</Term></Chip>
        {writing && <span className="flex items-center gap-1 text-xs text-ink/60"><Loader2 size={12} className="animate-spin" /> writing student-friendly text…</span>}
        {h.details_source === "ai" && <SourceBadge kind="ai" />}
        <span className="ml-auto flex items-center gap-1 text-xs font-semibold text-terracotta"><ShieldAlert size={14} /> Hypothesis, needs human validation</span>
      </div>
      <h3 className="font-display text-xl font-semibold leading-snug">{h.title}</h3>
      {h.note && <p className="text-xs italic text-ink/60">{h.note}</p>}

      {h.legacy ? <p className="text-sm">{h.hypothesis}</p> : (
        <div className="grid gap-x-8 md:grid-cols-2">
          <Block title="The problem, simply"><p>{h.problem}</p></Block>
          <Block title="Why it might matter"><p>{h.why_matters}</p></Block>
          <Block title="Potential research question"><p className="font-medium">{h.research_question}</p></Block>
          <Block title="Possible methodology"><p>{h.possible_methodology}</p></Block>
          <Block title="Datasets / resources"><Bullets items={h.datasets_resources} /></Block>
          <Block title="A possible student project"><p>{h.student_direction}</p></Block>
          <Block title="Feasibility considerations"><Bullets items={h.feasibility_considerations} /></Block>
          {h.coverage && <Block title="In your uploaded collection"><p>{h.coverage === "partly_discussed" ? "Other uploaded papers seem to discuss related topics, so it may already be partly addressed. Read them." : "Not clearly discussed in the other uploaded papers. This does not mean it is unexplored."}</p></Block>}
        </div>
      )}

      <Block title="Existing research evidence" badge="pdf">
        <div className="space-y-1.5">{h.evidence.map((e, i) => <Quote key={i} q={e} />)}</div>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-ink/60">Supporting papers:</span>
          {h.supporting_paper_ids.map((id) => <Link key={id} to={`/papers/${id}`}><Chip color="#A8C3B0" className="hover:underline">#{id} {titles[id] || ""}</Chip></Link>)}
        </div>
      </Block>

      <div className="grid gap-x-8 md:grid-cols-2">
        <Block title="Uncertainties"><Bullets items={h.uncertainties} /></Block>
        <Block title="How to validate"><ul className="space-y-1">{h.validation_steps.map((u, i) => <li key={i} className="flex gap-2"><span className="mt-1 h-3.5 w-3.5 shrink-0 rounded border-2 border-ink/60" />{u}</li>)}</ul></Block>
      </div>
      {h.confidence_reasons?.length > 0 && (
        <details className="text-xs text-ink/70"><summary className="cursor-pointer">Why this confidence level?</summary><Bullets items={h.confidence_reasons} /></details>
      )}

      {!h.legacy && <Feasibility h={h} onDone={onChanged} />}

      <div className="flex flex-wrap items-center gap-2 border-t border-ink/15 pt-3">
        <span className="text-xs text-ink/60">Your review:</span>
        {REVIEW.map(({ v, label, icon: Icon, bg }) => (
          <button key={v} onClick={() => onReview(h.id, h.review_status === v ? "new" : v)} aria-pressed={h.review_status === v}
            className="flex items-center gap-1.5 rounded-full border-2 border-ink/70 px-3 py-1 text-xs font-semibold transition hover:-translate-y-0.5"
            style={{ background: h.review_status === v ? bg : "#F9F6EE", boxShadow: h.review_status === v ? "inset 0 0 0 1px #2b2a26" : "none" }}>
            <Icon size={13} /> {label}
          </button>
        ))}
        <Link to={`/mentor?opportunity=${h.id}`} className="ml-auto"><Button variant="ghost" className="!px-3 !py-1"><GraduationCap size={14} /> Ask Research Mentor</Button></Link>
      </div>
    </Card>
  );
}

export default function Gaps() {
  const [data, setData] = useState(null);
  const [papers, setPapers] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("all");
  const [cat, setCat] = useState("all");
  const timer = useRef(null);

  const load = useCallback(async () => {
    try {
      const { data: d } = await api.get("/api/gaps");
      setData(d);
      clearTimeout(timer.current);
      if (d.enriching) timer.current = setTimeout(load, 2500);
    } catch (e) { setError(errMsg(e)); }
  }, []);
  useEffect(() => { load(); api.get("/api/papers").then((r) => setPapers(r.data)).catch(() => {}); return () => clearTimeout(timer.current); }, [load]);

  const titles = useMemo(() => Object.fromEntries(papers.map((p) => [p.id, p.title.length > 34 ? p.title.slice(0, 32) + "…" : p.title])), [papers]);
  const generate = async () => {
    setBusy(true); setError("");
    try { const { data: d } = await api.post("/api/gaps/generate"); setData(d); if (d.enriching) timer.current = setTimeout(load, 2500); }
    catch (e) { setError(errMsg(e)); } finally { setBusy(false); }
  };
  const review = async (id, review_status) => {
    try {
      const { data: h } = await api.patch(`/api/gaps/${id}`, { review_status });
      setData((d) => ({ ...d, hypotheses: d.hypotheses.map((x) => (x.id === id ? { ...x, review_status: h.review_status } : x)) }));
    } catch (e) { setError(errMsg(e)); }
  };

  const all = data?.hypotheses ?? [];
  const list = all.filter((h) => (filter === "all" || h.review_status === filter) && (cat === "all" || h.category === cat));
  const tabs = [["all", "All"], ["new", "To review"], ["accepted", "Accepted"], ["needs_investigation", "Needs investigation"], ["rejected", "Rejected"]];

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Research Opportunities" subtitle="Possible directions drawn from what your uploaded papers say about their limitations, methods and next steps. Each one shows the evidence behind it.">
        <Button onClick={generate} loading={busy}><Wand2 size={15} />{all.length ? "Regenerate" : "Find opportunities"}</Button>
      </PageHeader>

      <Card className="mb-5 !bg-[#fbf0dc]">
        <p className="flex items-start gap-2 text-sm"><Lightbulb size={18} className="mt-0.5 shrink-0 text-terracotta" />
          <span><b>{data?.disclaimer || "These are AI-assisted research hypotheses based on your uploaded papers, not verified discoveries of research gaps. Validate every direction against the wider scientific literature."}</b></span></p>
      </Card>
      <ErrorBox className="mb-4">{error}</ErrorBox>
      {data?.enriching && <p className="mb-3 flex items-center gap-2 font-hand text-2xl text-forest"><Loader2 size={18} className="animate-spin" /> Writing student-friendly descriptions… the evidence below is already final.</p>}

      {!data ? <Spinner label="Loading…" /> : all.length === 0 ? (
        <EmptyState title="No opportunities yet" action={<Button onClick={generate} loading={busy}><Wand2 size={15} /> Find opportunities</Button>}>
          You need at least two analyzed papers ({data.paper_count} so far). Opportunities come from four places: limitations that repeat, differences in methods, ideas never discussed together, and the authors' own future-work suggestions.
        </EmptyState>
      ) : (
        <>
          <div className="mb-2 flex flex-wrap gap-2">
            {tabs.map(([v, l]) => (
              <button key={v} onClick={() => setFilter(v)} className={`rounded-full border-2 border-ink/60 px-3 py-1 text-xs font-semibold ${filter === v ? "bg-forest text-ivory" : "bg-ivory"}`}>
                {l} ({v === "all" ? all.length : all.filter((h) => h.review_status === v).length})
              </button>
            ))}
          </div>
          <div className="mb-4 flex flex-wrap gap-2">
            {[["all", { label: "All categories" }], ...Object.entries(CATEGORY)].map(([k, c]) => (
              <button key={k} onClick={() => setCat(k)} title={c.blurb} className={`rounded-full border px-3 py-0.5 text-xs font-medium ${cat === k ? "border-ink bg-sand" : "border-ink/30 bg-ivory"}`}>{c.label}</button>
            ))}
          </div>
          <div className="space-y-5">
            {list.map((h, i) => <OpportunityCard key={h.id} h={h} titles={titles} onReview={review} onChanged={load} index={i} />)}
            {list.length === 0 && <p className="text-center font-hand text-2xl text-ink/60">Nothing here with these filters.</p>}
          </div>
        </>
      )}
    </div>
  );
}
