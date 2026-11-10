import { Brain, FileUp, Lightbulb, Network, ScanText } from "lucide-react";
import { REL } from "../constants";
import { Arrow, Squiggle } from "./Doodles";
import { Card } from "./ui";

const STEPS = [
  { icon: FileUp, title: "Upload PDFs", text: "Drop in several papers. Duplicates are skipped.", bg: "#EFE3D1" },
  { icon: ScanText, title: "Read sections", text: "Abstract, methods, results and limitations are found.", bg: "#A8C3B0" },
  { icon: Brain, title: "AI extracts", text: "A local model fills topics, methods, findings.", bg: "#D9A566" },
  { icon: Network, title: "Connect", text: "Embeddings and overlaps become graph edges.", bg: "#D9C5A8" },
  { icon: Lightbulb, title: "Hypotheses", text: "Possible gaps, with evidence you can check.", bg: "#E5B5A5" },
];

const EDGE_TEXT = {
  semantic_similarity: "Papers whose meaning is close",
  shared_topic: "Same topics or keywords",
  shared_methodology: "Same methods or algorithms",
  citation: "One lists the other in its references",
};

export default function HowItWorks() {
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-stretch justify-center gap-y-4">
        {STEPS.map((s, i) => (
          <div key={s.title} className="flex items-center">
            <Card className="rise w-44 text-center sketch-hover" style={{ animationDelay: `${i * 0.18}s`, background: s.bg }}>
              <s.icon className="mx-auto mb-1" size={26} />
              <p className="font-hand text-2xl font-bold leading-6">{s.title}</p>
              <p className="mt-1 text-xs leading-snug text-ink/80">{s.text}</p>
            </Card>
            {i < STEPS.length - 1 && <Arrow delay={0.3 + i * 0.18} className="hidden lg:block" />}
          </div>
        ))}
      </div>
      <div>
        <p className="mb-2 text-center font-hand text-2xl text-forest">How to read the graph's lines</p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Object.entries(REL).map(([k, r]) => (
            <Card key={k} soft className="py-3">
              <Squiggle color={r.color} dashed={!!r.dash} className="mb-1 h-4 w-full" />
              <p className="text-sm font-semibold">{r.label}</p>
              <p className="text-xs text-ink/70">{EDGE_TEXT[k]}</p>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
