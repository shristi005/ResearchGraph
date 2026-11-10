import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Background, BackgroundVariant, Controls, ReactFlow, ReactFlowProvider, useReactFlow } from "@xyflow/react";
import { Maximize2, RefreshCw, Search, Wand2 } from "lucide-react";
import { api, errMsg } from "../api";
import { REL } from "../constants";
import { Squiggle } from "../components/Doodles";
import GraphOverview from "../components/GraphOverview";
import { Button, Card, EmptyState, ErrorBox, PageHeader, Spinner, StepTracker } from "../components/ui";
import { placeLabels } from "../graph/labels";
import { forceLayout } from "../graph/layout";
import PaperNode from "../graph/PaperNode";
import RelEdge from "../graph/RelEdge";
import SidePanel from "../graph/SidePanel";

const nodeTypes = { paper: PaperNode };
const edgeTypes = { rel: RelEdge };
const GEN_STEPS = ["Embedding papers", "Comparing pairs", "Topics & methods", "Finding citations", "Drawing graph"];

function Inner() {
  const rf = useReactFlow();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [generating, setGenerating] = useState(false);
  const [genStep, setGenStep] = useState(0);
  const [summary, setSummary] = useState(null);
  const [enabled, setEnabled] = useState(new Set(Object.keys(REL)));
  const [query, setQuery] = useState("");
  const [sel, setSel] = useState(null);

  const load = useCallback(async () => {
    try { setData((await api.get("/api/graph")).data); setError(""); } catch (e) { setError(errMsg(e)); } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!generating) return;
    setGenStep(0);
    const t = setInterval(() => setGenStep((s) => Math.min(s + 1, GEN_STEPS.length - 1)), 2500);
    return () => clearInterval(t);
  }, [generating]);

  const generate = async () => {
    setGenerating(true); setError(""); setSummary(null);
    try { setSummary((await api.post("/api/graph/generate")).data); await load(); setSel(null); }
    catch (e) { setError(errMsg(e)); }
    finally { setGenerating(false); setTimeout(() => rf.fitView({ padding: 0.2, duration: 500 }), 80); }
  };

  const positions = useMemo(() => (data ? forceLayout(data.nodes, data.edges) : {}), [data]);
  const visibleEdges = useMemo(() => (data ? data.edges.filter((e) => enabled.has(e.type)) : []), [data, enabled]);

  const { rfNodes, rfEdges } = useMemo(() => {
    if (!data) return { rfNodes: [], rfEdges: [] };
    const q = query.trim().toLowerCase();
    const matches = new Set(q ? data.nodes.filter((n) => [n.title, ...n.topics, ...n.methods, ...n.authors].join(" ").toLowerCase().includes(q)).map((n) => n.id) : []);
    const focus = new Set();
    if (sel?.kind === "node") {
      focus.add(sel.id);
      visibleEdges.forEach((e) => { if (e.source === sel.id) focus.add(e.target); if (e.target === sel.id) focus.add(e.source); });
    }
    const groups = {};
    visibleEdges.forEach((e) => { const k = [e.source, e.target].sort().join("|"); (groups[k] ||= []).push(e.id); });
    const pickEdge = (id) => setSel({ kind: "edge", id });
    const rfNodes = data.nodes.map((n) => ({
      id: n.id, type: "paper", position: positions[n.id] || { x: 0, y: 0 },
      data: { ...n, match: matches.has(n.id), dim: (sel?.kind === "node" && !focus.has(n.id)) || (q && !matches.has(n.id)) },
    }));
    const withOffset = visibleEdges.map((e) => {
      const g = groups[[e.source, e.target].sort().join("|")];
      return { ...e, offset: (g.indexOf(e.id) - (g.length - 1) / 2) * 34, text: e.display?.short };
    });
    const labelT = placeLabels(data.nodes, withOffset, positions);
    const rfEdges = withOffset.map((e) => {
      const incident = sel?.kind === "node" && (e.source === sel.id || e.target === sel.id);
      return {
        id: e.id, source: e.source, target: e.target, type: "rel", selected: sel?.kind === "edge" && sel.id === e.id,
        data: { type: e.type, score: e.score, display: e.display, offset: e.offset, labelT: labelT[e.id], dim: sel?.kind === "node" && !incident, onPick: pickEdge },
      };
    });
    return { rfNodes, rfEdges };
  }, [data, positions, visibleEdges, query, sel]);

  const toggle = (k) => setEnabled((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const searchEnter = (e) => {
    if (e.key !== "Enter") return;
    const hit = rfNodes.filter((n) => n.data.match);
    if (hit.length) rf.fitView({ nodes: hit.map((n) => ({ id: n.id })), padding: 0.6, duration: 500, maxZoom: 1.1 });
  };
  const selectNode = (id) => { setSel({ kind: "node", id }); rf.fitView({ nodes: [{ id }], padding: 1.2, duration: 500, maxZoom: 1 }); };

  const nNodes = data?.nodes.length ?? 0;
  const counts = Object.fromEntries(Object.keys(REL).map((k) => [k, data?.edges.filter((e) => e.type === k).length ?? 0]));

  return (
    <div className="flex flex-col">
      <PageHeader title="Paper Relationship Graph" subtitle="Each node is an analyzed paper. Click a paper to see it explained in plain language, or click a line or its label to see why two papers are connected.">
        <Button onClick={generate} loading={generating}>{data?.meta.edge_count ? <RefreshCw size={15} /> : <Wand2 size={15} />}{data?.meta.edge_count ? "Regenerate graph" : "Generate graph"}</Button>
        <Button variant="ghost" onClick={() => rf.fitView({ padding: 0.2, duration: 500 })}><Maximize2 size={15} /> Fit to screen</Button>
      </PageHeader>
      <ErrorBox className="mb-3">{error}</ErrorBox>
      {summary && !generating && (
        <p className="mb-2 text-sm text-forest">Graph updated: {summary.edges} connections across {summary.papers} papers ({Object.entries(summary.by_type).map(([k, v]) => `${v} ${REL[k].short}`).join(", ") || "none found"}). Thresholds: similarity ≥ {summary.thresholds.similarity}.</p>
      )}

      {!loading && <GraphOverview paperCount={nNodes} refreshKey={data?.meta.edge_count} />}
      {loading ? <Spinner label="Loading graph…" /> : nNodes === 0 ? (
        <EmptyState title="Nothing to draw yet" action={<Link to="/papers"><Button>Go to My Papers</Button></Link>}>
          The graph shows analyzed papers. Upload papers and press “Analyze paper” on at least two of them.
        </EmptyState>
      ) : (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <label className="sketch sketch-soft flex items-center gap-2 px-3 py-1.5">
              <Search size={15} />
              <input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={searchEnter} placeholder="Search title, topic, method…" className="w-56 bg-transparent text-sm outline-none" aria-label="Search papers" />
            </label>
            {Object.entries(REL).map(([k, r]) => (
              <button key={k} onClick={() => toggle(k)} aria-pressed={enabled.has(k)}
                className={`flex items-center gap-2 rounded-full border-2 px-3 py-1 text-xs font-semibold transition ${enabled.has(k) ? "bg-ivory" : "bg-transparent opacity-50"}`} style={{ borderColor: r.color }}>
                <Squiggle color={r.color} dashed={!!r.dash} className="h-3 w-8" />{r.label} <span className="text-ink/55">{counts[k]}</span>
              </button>
            ))}
          </div>
          <div className="relative flex h-[78vh] min-h-[540px] gap-3">
            <Card soft className="relative min-h-0 flex-1 overflow-hidden !p-0">
              <ReactFlow nodes={rfNodes} edges={rfEdges} nodeTypes={nodeTypes} edgeTypes={edgeTypes}
                fitView fitViewOptions={{ padding: 0.2 }} minZoom={0.15} maxZoom={2} nodesConnectable={false}
                onNodeClick={(_, n) => setSel({ kind: "node", id: n.id })} onEdgeClick={(_, e) => setSel({ kind: "edge", id: e.id })}
                onPaneClick={() => setSel(null)} proOptions={{ hideAttribution: true }}>
                <Background variant={BackgroundVariant.Dots} gap={22} size={1.6} color="#D9C5A8" />
                <Controls showInteractive={false} />
              </ReactFlow>
              {data.meta.edge_count === 0 && !generating && (
                <div className="pointer-events-none absolute inset-x-0 top-4 flex justify-center"><span className="rounded-full border-2 border-ink/60 bg-mustard/80 px-4 py-1.5 font-hand text-xl">No connections yet. Press “Generate graph”.</span></div>
              )}
              {generating && (
                <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-4 bg-ivory/85 backdrop-blur-sm">
                  <p className="font-display text-2xl">Connecting your papers…</p>
                  <StepTracker steps={GEN_STEPS} active={genStep} />
                  <p className="max-w-xs text-center text-xs text-ink/60">Embedding the papers with the local model is the slow part.</p>
                </div>
              )}
            </Card>
            <SidePanel selection={sel} nodes={data.nodes} edges={data.edges} onClose={() => setSel(null)} onSelectNode={selectNode} onPickEdge={(id) => setSel({ kind: "edge", id })} />
          </div>
        </>
      )}
    </div>
  );
}

export default function GraphPage() {
  return <ReactFlowProvider><Inner /></ReactFlowProvider>;
}
