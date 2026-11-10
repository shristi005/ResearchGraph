import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { GraduationCap, Loader2, MessageSquarePlus, RefreshCw, Send, Trash2 } from "lucide-react";
import { api, errMsg } from "../api";
import { Button, Card, Chip, EmptyState, ErrorBox, PageHeader, Spinner } from "../components/ui";

function Answer({ m }) {
  const bySource = Object.fromEntries((m.sources || []).map((s) => [s.tag, s]));
  const parts = m.content.split(/(\[S\d+\])/g);
  return (
    <div>
      <p className="whitespace-pre-wrap text-sm leading-relaxed">
        {parts.map((t, i) => {
          const tag = t.match(/^\[(S\d+)\]$/)?.[1];
          if (!tag || !bySource[tag]) return <Fragment key={i}>{t}</Fragment>;
          const s = bySource[tag];
          return <a key={i} href={`#src-${m.id}-${tag}`} title={`${s.paper_title}, page ${s.page ?? "?"}`} className="mx-0.5 rounded-full border border-forest bg-[#e6efe9] px-1.5 text-[11px] font-semibold text-forest no-underline">{tag}</a>;
        })}
      </p>
      {m.warnings?.length > 0 && <div className="mt-2 rounded-lg bg-[#fbf0dc] p-2 text-xs text-ink/80">{m.warnings.map((w, i) => <p key={i}>⚠ {w}</p>)}</div>}
      {m.sources?.length > 0 && (
        <details className="mt-2 text-xs">
          <summary className="cursor-pointer font-semibold text-forest">Sources from your papers ({m.sources.filter((s) => s.cited).length} cited of {m.sources.length} retrieved)</summary>
          <ul className="mt-1 space-y-1.5">
            {m.sources.map((s) => (
              <li key={s.tag} id={`src-${m.id}-${s.tag}`} className={`rounded-lg border p-2 ${s.cited ? "border-forest bg-[#e6efe9]/60" : "border-ink/15 bg-ivory/70"}`}>
                <span className="font-semibold">[{s.tag}] <Link to={`/papers/${s.paper_id}`} className="hover:underline">{s.paper_title}</Link> · page {s.page ?? "n/a"} · {s.section.replaceAll("_", " ")}{s.cited ? " · cited" : ""}</span>
                <p className="italic text-ink/75">“{s.text.length > 320 ? s.text.slice(0, 320) + "…" : s.text}”</p>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

export default function Mentor() {
  const [params] = useSearchParams();
  const opportunityId = params.get("opportunity") ? Number(params.get("opportunity")) : null;
  const [papers, setPapers] = useState([]);
  const [selected, setSelected] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [convs, setConvs] = useState([]);
  const [cid, setCid] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [prep, setPrep] = useState("loading");
  const [error, setError] = useState("");
  const bottom = useRef(null);

  const loadConvs = useCallback(() => api.get("/api/mentor/conversations").then((r) => setConvs(r.data)).catch(() => {}), []);

  useEffect(() => {
    api.get("/api/papers").then((r) => { const a = r.data.filter((p) => p.has_extraction); setPapers(a); setSelected(new Set(a.map((p) => p.id))); })
      .catch((e) => setError(errMsg(e)));
    api.get("/api/mentor/suggestions").then((r) => setSuggestions(r.data.suggestions)).catch(() => {});
    loadConvs();
    api.post("/api/mentor/index").then(() => setPrep("ready")).catch((e) => { setPrep("error"); setError(errMsg(e)); });
  }, [loadConvs]);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, busy]);

  const send = async (text, regenerate = false) => {
    if (busy) return;
    setBusy(true); setError("");
    if (!regenerate) { setMessages((m) => [...m, { id: `tmp${Date.now()}`, role: "user", content: text }]); setInput(""); }
    else setMessages((m) => (m[m.length - 1]?.role === "assistant" ? m.slice(0, -1) : m));
    try {
      const { data } = await api.post("/api/mentor/chat", {
        message: regenerate ? null : text, conversation_id: cid, regenerate, opportunity_id: opportunityId,
        paper_ids: selected && selected.size !== papers.length ? [...selected] : null,
      });
      setCid(data.conversation_id);
      setMessages((m) => [...m, data.message]);
      loadConvs();
    } catch (e) { setError(errMsg(e)); } finally { setBusy(false); }
  };
  const open = async (id) => {
    try { const { data } = await api.get(`/api/mentor/conversations/${id}`); setCid(id); setMessages(data.messages); setError(""); } catch (e) { setError(errMsg(e)); }
  };
  const remove = async (id) => { await api.delete(`/api/mentor/conversations/${id}`); if (id === cid) { setCid(null); setMessages([]); } loadConvs(); };
  const toggle = (id) => setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });

  if (selected && papers.length === 0 && !error) return (
    <div><PageHeader title="Research Mentor" /><EmptyState title="Analyze a paper first" action={<Link to="/papers"><Button>Go to My Papers</Button></Link>}>Research Mentor answers from your own papers, so it needs at least one analyzed paper.</EmptyState></div>
  );

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Research Mentor" subtitle="Ask questions about your uploaded papers. Answers point to the passage and page they come from, and say when your papers do not contain the answer." />
      <div className="grid gap-4 lg:grid-cols-[15rem_1fr]">
        <aside className="space-y-4">
          <Card soft className="!p-3">
            <p className="mb-1 font-hand text-xl font-bold">Papers in context</p>
            {papers.map((p) => (
              <label key={p.id} className="mb-1 flex cursor-pointer items-start gap-2 text-xs">
                <input type="checkbox" className="mt-0.5" checked={selected?.has(p.id) ?? false} onChange={() => toggle(p.id)} /> <span>{p.title}</span>
              </label>
            ))}
          </Card>
          <Card soft className="!p-3">
            <div className="mb-1 flex items-center justify-between"><p className="font-hand text-xl font-bold">Conversations</p>
              <button className="rounded p-1 hover:bg-beige" title="New conversation" aria-label="New conversation" onClick={() => { setCid(null); setMessages([]); }}><MessageSquarePlus size={16} /></button></div>
            {convs.length === 0 && <p className="text-xs italic text-ink/50">None yet.</p>}
            {convs.map((c) => (
              <div key={c.id} className={`group flex items-center gap-1 rounded-lg px-2 py-1 text-xs ${c.id === cid ? "bg-sage/50" : "hover:bg-beige"}`}>
                <button className="flex-1 truncate text-left" onClick={() => open(c.id)} title={c.title}>{c.title}</button>
                <button className="opacity-0 group-hover:opacity-100" aria-label="Delete conversation" onClick={() => remove(c.id)}><Trash2 size={12} /></button>
              </div>
            ))}
          </Card>
        </aside>

        <section className="flex min-h-[60vh] flex-col">
          {opportunityId && <p className="mb-2 rounded-lg bg-[#fbf0dc] p-2 text-xs">Discussing research opportunity #{opportunityId}. <Link to="/gaps" className="underline">Back to opportunities</Link></p>}
          {prep === "loading" && <p className="mb-2 flex items-center gap-2 text-xs text-ink/60"><Loader2 size={13} className="animate-spin" /> Preparing your papers for search (first time only)…</p>}
          <Card className="flex-1 space-y-4 overflow-y-auto !p-4" style={{ maxHeight: "62vh" }}>
            {messages.length === 0 && (
              <div>
                <p className="font-hand text-2xl text-forest">What would you like to understand?</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {suggestions.map((s) => <button key={s} onClick={() => send(s)} disabled={busy || prep === "loading"} className="rounded-full border-2 border-ink/50 bg-ivory px-3 py-1 text-left text-xs font-medium hover:bg-beige disabled:opacity-50">{s}</button>)}
                </div>
              </div>
            )}
            {messages.map((m, i) => (
              <div key={m.id} className={m.role === "user" ? "ml-auto max-w-[85%] rounded-2xl bg-sage/50 p-3 text-sm" : "max-w-[95%] rounded-2xl border border-ink/20 bg-ivory p-3"}>
                {m.role === "user" ? m.content : <Answer m={m} />}
                {m.role === "assistant" && i === messages.length - 1 && !busy && (
                  <button className="mt-2 flex items-center gap-1 text-xs text-forest hover:underline" onClick={() => send(null, true)}><RefreshCw size={12} /> Regenerate answer</button>
                )}
              </div>
            ))}
            {busy && <p className="flex items-center gap-2 text-sm text-ink/60"><Loader2 size={15} className="animate-spin" /> Looking through your papers…</p>}
            <div ref={bottom} />
          </Card>
          <ErrorBox className="mt-2">{error}</ErrorBox>
          <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (input.trim()) send(input.trim()); }}>
            <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about your papers…" aria-label="Your question"
              className="sketch sketch-soft flex-1 bg-ivory px-4 py-2.5 text-sm outline-none" disabled={busy} />
            <Button type="submit" loading={busy} disabled={!input.trim() || prep === "loading"}><Send size={15} /> Ask</Button>
          </form>
          <p className="mt-1 text-xs text-ink/50">Answers are AI-written from retrieved passages. “From your papers” is backed by a cited passage; “My inference” is the AI's own reasoning. Verify before relying on it.</p>
        </section>
      </div>
    </div>
  );
}
