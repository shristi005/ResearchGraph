import { AlertTriangle, Loader2 } from "lucide-react";
import { STATUS } from "../constants";

export function Card({ className = "", soft, children, ...rest }) {
  return (
    <div className={`sketch ${soft ? "sketch-soft" : ""} p-5 ${className}`} {...rest}>
      {children}
    </div>
  );
}

const VARIANTS = {
  primary: "bg-forest text-ivory hover:bg-[#2f4a3d]",
  ghost: "bg-ivory text-ink hover:bg-beige",
  warm: "bg-mustard text-ink hover:bg-[#c8944f]",
  danger: "bg-ivory text-terracotta hover:bg-[#f3dcd2]",
};

export function Button({ variant = "primary", className = "", loading, children, ...rest }) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || loading}
      className={`relative inline-flex items-center gap-2 rounded-xl border-2 border-ink/80 px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${VARIANTS[variant]} ${className}`}
    >
      {loading && <Loader2 size={15} className="animate-spin" />}
      {children}
    </button>
  );
}

export function Chip({ children, color = "#EFE3D1", className = "" }) {
  return (
    <span className={`inline-block rounded-full border border-ink/25 px-2.5 py-0.5 text-xs font-medium ${className}`} style={{ background: color }}>
      {children}
    </span>
  );
}

export function StatusPill({ status }) {
  const s = STATUS[status] || STATUS.uploaded;
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-ink/30 px-2.5 py-0.5 text-xs font-semibold" style={{ background: s.bg }}>
      {status === "analyzing" && <span className="pulse-dot h-2 w-2 rounded-full bg-ink" />}
      {s.label}
    </span>
  );
}

export function ErrorBox({ children, className = "" }) {
  if (!children) return null;
  return (
    <div className={`flex items-start gap-2 rounded-xl border-2 border-terracotta/70 bg-[#f6e3da] p-3 text-sm ${className}`} role="alert">
      <AlertTriangle size={18} className="mt-0.5 shrink-0 text-terracotta" />
      <div>{children}</div>
    </div>
  );
}

export function EmptyState({ title, children, action }) {
  return (
    <Card soft className="mx-auto max-w-xl text-center">
      <p className="font-hand text-3xl text-forest">{title}</p>
      <div className="mt-1 text-sm text-ink/75">{children}</div>
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </Card>
  );
}

export function Spinner({ label }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-ink/70">
      <Loader2 className="animate-spin" size={18} /> {label}
    </div>
  );
}

export function PageHeader({ title, subtitle, children }) {
  return (
    <div className="rise mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="font-display text-3xl font-semibold">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-sm text-ink/70">{subtitle}</p>}
      </div>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

/** Animated hand-drawn step tracker used while work is running. */
export function StepTracker({ steps, active }) {
  return (
    <ol className="flex flex-wrap items-start justify-center gap-x-6 gap-y-3">
      {steps.map((s, i) => {
        const done = i < active, now = i === active;
        return (
          <li key={s} className="flex w-28 flex-col items-center gap-1 text-center">
            <span
              className={`flex h-9 w-9 items-center justify-center rounded-full border-2 border-ink/80 text-sm font-bold ${
                done ? "bg-forest text-ivory" : now ? "bg-mustard" : "bg-ivory"
              }`}
            >
              {done ? "✓" : now ? <span className="pulse-dot h-2.5 w-2.5 rounded-full bg-ink" /> : i + 1}
            </span>
            <span className={`font-hand text-lg leading-tight ${now ? "font-bold" : ""}`}>{s}</span>
          </li>
        );
      })}
    </ol>
  );
}

/** Technical term with a plain-language tooltip (works on hover and keyboard focus). */
export function Term({ hint, children }) {
  return (
    <span tabIndex={0} title={hint} aria-label={`${children}: ${hint}`}
      className="cursor-help underline decoration-dotted decoration-ink/50 underline-offset-2">{children}</span>
  );
}

/** Tells the reader where a piece of text comes from. */
export function SourceBadge({ kind }) {
  const pdf = kind === "pdf";
  return (
    <span className="ml-2 inline-block rounded-full border px-2 py-px align-middle text-[10px] font-semibold uppercase tracking-wide"
      style={{ borderColor: pdf ? "#3F5D4E" : "#B06A4F", color: pdf ? "#3F5D4E" : "#B06A4F", background: pdf ? "#e6efe9" : "#f6e3da" }}
      title={pdf ? "Taken word for word from the PDF" : "Written by the local AI model from the paper's extracted data. Check it against the paper."}>
      {pdf ? "From the PDF" : "AI explanation"}
    </span>
  );
}

export function Quote({ q, className = "" }) {
  return (
    <blockquote className={`rounded-lg border border-ink/20 bg-ivory/80 p-2 text-sm ${className}`}>
      <span className="text-xs font-semibold text-forest">
        {q.paper_title ? `${q.paper_title} · ` : q.paper_id ? `Paper #${q.paper_id} · ` : ""}
        {q.page ? `page ${q.page}` : "page n/a"}{q.section ? ` · ${String(q.section).replaceAll("_", " ")}` : ""}
      </span>
      <p className="italic">“{q.quote || q.text}”</p>
    </blockquote>
  );
}

export function Block({ title, children, badge }) {
  return (
    <section className="mb-3">
      <h4 className="font-hand text-xl font-bold leading-6">{title}{badge && <SourceBadge kind={badge} />}</h4>
      <div className="text-sm leading-relaxed">{children}</div>
    </section>
  );
}

export const Bullets = ({ items, empty = "Not stated." }) =>
  items?.length ? <ul className="list-disc space-y-1 pl-5">{items.map((x, i) => <li key={i}>{x}</li>)}</ul> : <p className="italic text-ink/50">{empty}</p>;
