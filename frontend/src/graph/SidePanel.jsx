import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, RefreshCw, X } from "lucide-react";
import { api, errMsg } from "../api";
import { REL } from "../constants";
import { Block, Bullets, Button, Chip, ErrorBox, Quote, SourceBadge, Spinner, Term } from "../components/ui";

function NodeDetail({ node, onSelectNode, onPickEdge }) {
  const [a, setA] = useState(null);
  const [ex, setEx] = useState(null);
  const [nb, setNb] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const loadExplanation = useCallback(async (refresh = false) => {
    setBusy(true);
    try { setEx((await api.get(`/api/papers/${node.paper_id}/explanation`, { params: refresh ? { refresh: true } : {} })).data); }
    catch (e) { setEx({ error: errMsg(e) }); }
    finally { setBusy(false); }
  }, [node.paper_id]);

  useEffect(() => {
    setA(null); setNb(null); setEx(null); setErr("");
    Promise.all([api.get(`/api/papers/${node.paper_id}/analysis`), api.get(`/api/graph/paper/${node.paper_id}/neighbors`)])
      .then(([x, y]) => { setA(x.data.analysis); setNb(y.data.neighbors); })
      .catch((e) => setErr(errMsg(e)));
    loadExplanation(false);
  }, [node.paper_id, loadExplanation]);

  const ai = ex?.ai;
  return (
    <>
      <h2 className="pr-8 font-display text-xl font-semibold leading-snug">{node.title}</h2>
      <p className="mb-3 text-xs text-ink/65">{[a?.authors?.join(", "), node.year, a?.article_type].filter(Boolean).join(" · ") || "Authors / year not detected"}</p>
      <ErrorBox>{err}</ErrorBox>

      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink/50">In plain language</p>
        <button className="flex items-center gap-1 text-xs text-forest hover:underline" onClick={() => loadExplanation(true)} disabled={busy}><RefreshCw size={12} className={busy ? "animate-spin" : ""} /> Regenerate</button>
      </div>
      {!ex && <Spinner label="Writing a student-friendly explanation…" />}
      {ex?.error && <ErrorBox className="mb-3">The AI explanation is unavailable: {ex.error} The extracted details below are still shown.</ErrorBox>}
      {ai && (
        <div className={`mb-4 rounded-xl bg-[#fbf0dc]/70 p-3 ${busy ? "opacity-50" : ""}`}>
          <Block title="1. What is this paper about?" badge="ai"><p>{ai.about || "Not stated."}</p></Block>
          <Block title="2. What problem does it address?"><p>{ai.problem || "Not stated."}</p></Block>
          <Block title="3. Why is this problem important?"><p>{ai.importance || "Not stated."}</p></Block>
          <Block title="4. What approach did the researchers use?"><p>{ai.approach || "Not stated."}</p></Block>
          <Block title="5. What did they find or conclude?"><p>{ai.findings || "Not stated."}</p></Block>
          <Block title="6. What are the limitations?"><p>{ai.limitations || "Not stated."}</p></Block>
          <Block title="7. What should a student understand?"><Bullets items={ai.student_takeaways} empty="Nothing listed." /></Block>
          <Block title="8. How does it connect to your other papers?"><p>{ai.connections || "No connections yet."}</p></Block>
        </div>
      )}

      <div className="mb-3">
        <p className="font-hand text-xl font-bold">Connected papers ({nb?.length ?? 0})</p>
        {nb?.length === 0 && <p className="text-sm italic text-ink/55">No connections yet. Try “Regenerate graph”.</p>}
        <ul className="space-y-2">
          {nb?.map((n) => (
            <li key={n.id} className="rounded-xl border border-ink/25 bg-beige/60 p-2">
              <button className="text-left text-sm font-semibold hover:text-forest" onClick={() => onSelectNode(n.id)}>{n.title}</button>
              <div className="mt-1 flex flex-wrap gap-1">
                {n.relationships.map((r) => (
                  <button key={r.id} onClick={() => onPickEdge(r.id)} title={r.display.detail} className="rounded-full border px-2 py-px text-[11px] font-medium" style={{ borderColor: REL[r.type].color, background: "#F9F6EE" }}>
                    {r.display.short}
                  </button>
                ))}
              </div>
            </li>
          ))}
        </ul>
      </div>

      <details className="mb-3 rounded-xl border-2 border-forest/40 bg-[#e6efe9]/50 p-3" open>
        <summary className="cursor-pointer font-semibold">Technical details<SourceBadge kind="pdf" /></summary>
        {!a ? <Spinner label="Loading…" /> : (
          <div className="mt-2">
            <p className="mb-2 text-xs text-ink/60">Extracted from the PDF by the analysis step, not rewritten by the explanation above.</p>
            <Block title="Extracted topics"><div className="flex flex-wrap gap-1.5">{a.topics.map((t, i) => <Chip key={i} color="#A8C3B0">{t}</Chip>)}{!a.topics.length && <span className="italic text-ink/50">None.</span>}</div></Block>
            <Block title="Methodologies"><div className="flex flex-wrap gap-1.5">{[...a.methodologies, ...a.algorithms].map((t, i) => <Chip key={i} color="#E5B5A5">{t}</Chip>)}{!a.methodologies.length && !a.algorithms.length && <span className="italic text-ink/50">None.</span>}</div></Block>
            <Block title="Findings"><Bullets items={a.findings} /></Block>
            <Block title="Limitations"><Bullets items={a.limitations} empty="No limitations explicitly stated." /></Block>
            <Block title="Future work"><Bullets items={a.future_work} empty="No future work explicitly stated." /></Block>
            <Block title="Source evidence (quotes with page numbers)">
              {a.evidence.filter((e) => e.verified && ["limitations", "future_work", "findings"].includes(e.field)).slice(0, 6).map((e, i) => (
                <Quote key={i} q={{ quote: e.quote, page: e.page, section: e.section }} className="mb-1.5" />
              ))}
              {!a.evidence.some((e) => e.verified) && <p className="italic text-ink/50">No statement could be matched to a sentence in the PDF.</p>}
            </Block>
            <p className="text-xs text-ink/55">Extraction confidence: {a.extraction_confidence ?? "n/a"} · Abstract: {a.abstract_source ?? "not found"}</p>
          </div>
        )}
      </details>
      <Link to={`/papers/${node.paper_id}`}><Button className="w-full justify-center">Full paper analysis <ArrowRight size={14} /></Button></Link>
    </>
  );
}

function EdgeDetail({ edge, onSelectNode }) {
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async (refresh = false) => {
    setBusy(true);
    try { setD((await api.get(`/api/graph/edge/${edge.id}/detail`, { params: refresh ? { refresh: true } : {} })).data); }
    catch (e) { setD({ fatal: errMsg(e) }); }
    finally { setBusy(false); }
  }, [edge.id]);
  useEffect(() => { setD(null); load(false); }, [load]);

  const r = REL[edge.type];
  if (!d) return <Spinner label="Explaining this connection…" />;
  if (d.fatal) return <ErrorBox>{d.fatal}</ErrorBox>;
  const ai = d.ai;
  return (
    <>
      <span className="inline-block rounded-full border-2 px-3 py-0.5 text-sm font-semibold" style={{ borderColor: r.color }}>{d.display.label}</span>
      <p className="mt-1 text-sm font-semibold">{d.display.strength}</p>
      <p className="mb-3 text-sm text-ink/80">{d.display.detail}</p>
      <div className="mb-3 space-y-1.5">
        {d.papers.map((p, i) => (
          <button key={p.id} className="block w-full rounded-xl border border-ink/25 bg-beige/60 p-2 text-left text-sm font-semibold hover:text-forest" onClick={() => onSelectNode(`paper_${p.id}`)}>
            <span className="text-xs font-normal text-ink/60">{edge.type === "citation" ? (i === 0 ? "Cites → " : "Cited paper: ") : `Paper ${"AB"[i]}: `}</span>{p.title}
          </button>
        ))}
      </div>

      <div className="mb-1 flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink/50">In plain language</p>
        <button className="flex items-center gap-1 text-xs text-forest hover:underline" onClick={() => load(true)} disabled={busy}><RefreshCw size={12} className={busy ? "animate-spin" : ""} /> Regenerate</button>
      </div>
      {d.error && <ErrorBox className="mb-3">The AI explanation is unavailable: {d.error} The facts below come straight from the PDFs.</ErrorBox>}
      {ai && (
        <div className={`mb-3 rounded-xl bg-[#fbf0dc]/70 p-3 ${busy ? "opacity-50" : ""}`}>
          <Block title="Why are these papers connected?" badge="ai"><p>{ai.connected}</p></Block>
          <Block title="What do they have in common?"><Bullets items={ai.in_common} empty="Nothing specific listed." /></Block>
          <Block title="How are they different?"><Bullets items={ai.differences} empty="Nothing specific listed." /></Block>
          <Block title="Why should a student read both?"><p>{ai.why_read_both}</p></Block>
        </div>
      )}
      <Block title={<>What does this <Term hint={d.display.numeric ? "A model-derived closeness score between 0 and 1" : "How the connection was measured"}>measure</Term> mean?</>}>
        <p>{d.display.score_meaning}</p>
      </Block>
      <Block title="Evidence from the papers" badge="pdf">
        {d.evidence.length === 0 ? <p className="italic text-ink/50">No quotable sentence was found for this connection.</p>
          : <div className="space-y-1.5">{d.evidence.map((q, i) => <Quote key={i} q={q} />)}</div>}
      </Block>
    </>
  );
}

export default function SidePanel({ selection, nodes, edges, onClose, onSelectNode, onPickEdge }) {
  if (!selection) return null;
  const node = selection.kind === "node" ? nodes.find((n) => n.id === selection.id) : null;
  const edge = selection.kind === "edge" ? edges.find((e) => e.id === selection.id) : null;
  if (!node && !edge) return null;
  return (
    <aside className="sketch rise absolute inset-x-2 bottom-2 z-20 max-h-[60%] overflow-y-auto p-4 md:static md:max-h-none md:w-[26rem] md:shrink-0">
      <button className="absolute right-3 top-3 rounded-full p-1 hover:bg-beige" onClick={onClose} aria-label="Close panel"><X size={18} /></button>
      {node ? <NodeDetail node={node} onSelectNode={onSelectNode} onPickEdge={onPickEdge} /> : <EdgeDetail edge={edge} onSelectNode={onSelectNode} />}
    </aside>
  );
}
