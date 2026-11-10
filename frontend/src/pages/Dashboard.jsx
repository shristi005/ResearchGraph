import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Check, FileText, Lightbulb, Network, Share2 } from "lucide-react";
import { api } from "../api";
import { GraphDoodle, Leaf, Sparkle } from "../components/Doodles";
import HowItWorks from "../components/HowItWorks";
import PaperCard from "../components/PaperCard";
import { Button, Card, ErrorBox } from "../components/ui";
import { usePapers } from "../usePapers";

export default function Dashboard() {
  const { papers, error } = usePapers();
  const [edges, setEdges] = useState(0);
  const [gaps, setGaps] = useState(0);

  useEffect(() => {
    api.get("/api/graph").then((r) => setEdges(r.data.meta.edge_count)).catch(() => {});
    api.get("/api/gaps").then((r) => setGaps(r.data.hypotheses.length)).catch(() => {});
  }, []);

  const analyzed = papers.filter((p) => p.has_extraction).length;
  const stats = [
    { icon: FileText, n: papers.length, label: "Papers", bg: "#EFE3D1" },
    { icon: Check, n: analyzed, label: "Analyzed", bg: "#A8C3B0" },
    { icon: Share2, n: edges, label: "Connections", bg: "#D9C5A8" },
    { icon: Lightbulb, n: gaps, label: "Opportunities", bg: "#D9A566" },
  ];
  const steps = [
    { done: papers.length > 0, text: "Upload your papers", to: "/papers" },
    { done: analyzed >= 2, text: "Analyze at least two", to: "/papers" },
    { done: edges > 0, text: "Generate the graph", to: "/graph" },
    { done: gaps > 0, text: "Explore research opportunities", to: "/gaps" },
  ];
  const next = steps.find((s) => !s.done);

  return (
    <div className="space-y-8">
      <section className="relative overflow-hidden">
        <Leaf className="absolute -left-2 top-4 hidden h-28 w-16 sm:block" />
        <div className="grid items-center gap-6 md:grid-cols-[1.1fr_1fr] md:pl-12">
          <div className="rise">
            <h1 className="font-display text-4xl font-bold leading-tight md:text-5xl">
              See the bigger picture of your <span className="italic text-terracotta">research.</span>
            </h1>
            <p className="mt-3 max-w-md text-ink/75">Upload papers, let a local AI read them, and watch how they connect. Everything stays on your computer.</p>
            <div className="mt-5 flex flex-wrap gap-3">
              <Link to="/papers"><Button>Start exploring <ArrowRight size={15} /></Button></Link>
              <Link to="/graph"><Button variant="ghost"><Network size={15} /> Open the graph</Button></Link>
            </div>
          </div>
          <div className="relative"><GraphDoodle className="bob mx-auto w-full max-w-sm" /><Sparkle className="absolute right-6 top-0 h-9 w-9" /></div>
        </div>
      </section>

      <ErrorBox>{error}</ErrorBox>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((s, i) => (
          <Card key={s.label} className="rise flex items-center gap-3 sketch-hover" style={{ background: s.bg, animationDelay: `${i * 0.08}s` }}>
            <s.icon size={26} />
            <div><p className="font-display text-3xl font-bold leading-none">{s.n}</p><p className="text-xs">{s.label}</p></div>
          </Card>
        ))}
      </section>

      <Card className="rise">
        <p className="font-hand text-3xl text-forest">{next ? "Your next step" : "All steps done. Keep exploring!"}</p>
        <ol className="mt-2 flex flex-wrap gap-x-8 gap-y-2">
          {steps.map((s) => (
            <li key={s.text} className="flex items-center gap-2 text-sm">
              <span className={`flex h-6 w-6 items-center justify-center rounded-full border-2 border-ink/70 text-xs ${s.done ? "bg-forest text-ivory" : s === next ? "bg-mustard" : ""}`}>{s.done ? "✓" : ""}</span>
              {s === next ? <Link to={s.to} className="font-semibold underline decoration-wavy decoration-mustard">{s.text}</Link> : <span className={s.done ? "text-ink/55 line-through" : ""}>{s.text}</span>}
            </li>
          ))}
        </ol>
      </Card>

      <section>
        <h2 className="mb-3 text-center font-display text-2xl font-semibold">How ResearchGraph works</h2>
        <HowItWorks />
      </section>

      {papers.length > 0 && (
        <section>
          <div className="mb-3 flex items-center justify-between"><h2 className="font-display text-2xl font-semibold">Recent papers</h2><Link to="/papers" className="text-sm text-forest hover:underline">View all →</Link></div>
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
            {papers.slice(-3).reverse().map((p, i) => <PaperCard key={p.id} paper={p} index={i} onAnalyze={() => {}} onDelete={() => {}} />)}
          </div>
        </section>
      )}
    </div>
  );
}
