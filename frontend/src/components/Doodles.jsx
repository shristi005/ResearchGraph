/** Small hand-drawn SVG doodles. All strokes use the shared #rough filter from <SketchDefs/>. */
const stroke = { fill: "none", stroke: "#2b2a26", strokeWidth: 2.4, strokeLinecap: "round", strokeLinejoin: "round" };

export function SketchDefs() {
  return (
    <svg width="0" height="0" className="absolute" aria-hidden="true">
      <defs>
        <filter id="rough" x="-5%" y="-5%" width="110%" height="110%">
          <feTurbulence type="fractalNoise" baseFrequency="0.025" numOctaves="2" seed="4" result="n" />
          <feDisplacementMap in="SourceGraphic" in2="n" scale="3.2" />
        </filter>
      </defs>
    </svg>
  );
}

export function Leaf({ className = "", flip }) {
  return (
    <svg viewBox="0 0 80 120" className={`sway ${className}`} style={flip ? { transform: "scaleX(-1)" } : null} aria-hidden="true">
      <g filter="url(#rough)">
        <path d="M40 115 C38 80 40 50 42 12" {...stroke} />
        {[28, 48, 68, 88].map((y, i) => (
          <g key={y}>
            <path d={`M40 ${y} C${18 - i * 2} ${y - 6} ${14} ${y - 22} ${24} ${y - 26} C${34} ${y - 22} ${38} ${y - 10} 40 ${y}`} {...stroke} fill="#A8C3B0" />
            <path d={`M41 ${y + 4} C${62 + i * 2} ${y - 2} ${66} ${y - 18} ${56} ${y - 22} C${46} ${y - 18} ${42} ${y - 6} 41 ${y + 4}`} {...stroke} fill="#A8C3B0" />
          </g>
        ))}
      </g>
    </svg>
  );
}

export function Sparkle({ className = "" }) {
  return (
    <svg viewBox="0 0 40 40" className={`bob ${className}`} aria-hidden="true">
      <g filter="url(#rough)">
        <path d="M20 3 L23 16 L36 20 L23 24 L20 37 L17 24 L4 20 L17 16 Z" {...stroke} fill="#D9A566" />
      </g>
    </svg>
  );
}

/** A little paper-and-graph illustration for the hero / empty states. */
export function GraphDoodle({ className = "" }) {
  return (
    <svg viewBox="0 0 360 260" className={className} aria-hidden="true">
      <g filter="url(#rough)">
        <rect x="30" y="40" width="130" height="170" rx="8" {...stroke} fill="#F9F6EE" transform="rotate(-6 95 125)" />
        <path d="M52 80 H130 M52 100 H140 M52 120 H116 M52 140 H136" {...stroke} className="draw" pathLength="1" />
        <rect x="150" y="70" width="150" height="150" rx="8" {...stroke} fill="#EFE3D1" transform="rotate(4 225 145)" />
        <circle cx="190" cy="120" r="13" {...stroke} fill="#A8C3B0" />
        <circle cx="262" cy="108" r="13" {...stroke} fill="#D9A566" />
        <circle cx="236" cy="182" r="13" {...stroke} fill="#B06A4F" />
        <path d="M202 119 L249 110 M196 132 L228 170 M257 121 L243 169" {...stroke} className="draw" pathLength="1" style={{ animationDelay: ".5s" }} />
        <path d="M300 40 q20 -22 40 0" {...stroke} />
      </g>
    </svg>
  );
}

export function Arrow({ delay = 0, className = "" }) {
  return (
    <svg viewBox="0 0 70 30" className={`h-7 w-16 shrink-0 ${className}`} aria-hidden="true">
      <g filter="url(#rough)">
        <path d="M4 16 C20 6 40 24 62 14 M52 5 L63 14 L50 24" {...stroke} className="draw" pathLength="1" style={{ animationDelay: `${delay}s` }} />
      </g>
    </svg>
  );
}

export function Squiggle({ color, dashed, className = "" }) {
  return (
    <svg viewBox="0 0 120 16" className={className} aria-hidden="true">
      <path d="M3 8 C20 0 30 16 50 8 S85 0 117 8" fill="none" stroke={color} strokeWidth="4" strokeLinecap="round" strokeDasharray={dashed ? "8 7" : undefined} />
    </svg>
  );
}
