import { useEffect, useState } from "react";
import { Navigate, NavLink, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { FileText, GraduationCap, LayoutDashboard, Lightbulb, Network, Menu, X, LogOut } from "lucide-react";
import { api } from "./api";
import { useAuth } from "./auth/AuthContext";
import { Leaf, SketchDefs } from "./components/Doodles";
import { ErrorBox } from "./components/ui";
import Dashboard from "./pages/Dashboard";
import Papers from "./pages/Papers";
import PaperAnalysis from "./pages/PaperAnalysis";
import GraphPage from "./pages/GraphPage";
import Gaps from "./pages/Gaps";
import Mentor from "./pages/Mentor";
import { ForgotPassword, Login, ResetPassword, Signup } from "./pages/Auth";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/papers", label: "My Papers", icon: FileText },
  { to: "/graph", label: "Research Graph", icon: Network },
  { to: "/gaps", label: "Research Opportunities", icon: Lightbulb },
  { to: "/mentor", label: "Research Mentor", icon: GraduationCap },
];

function AiBanner() {
  const [st, setSt] = useState(null);
  const [down, setDown] = useState(false);
  useEffect(() => {
    let alive = true;
    const check = () =>
      api.get("/api/ai/status").then((r) => alive && (setSt(r.data), setDown(false))).catch(() => alive && setDown(true));
    check();
    const t = setInterval(check, 20000);
    return () => { alive = false; clearInterval(t); };
  }, []);
  if (down) return <ErrorBox className="mb-4">Cannot reach the ResearchGraph backend. Locally: <code>uvicorn app.main:app --reload --port 8000</code>. If it is hosted on a free plan it may be waking up (up to a minute); this page retries by itself.</ErrorBox>;
  if (st && (!st.llm_ready || !st.embedding_ready))
    return <ErrorBox className="mb-4"><b>AI setup needed.</b> {st.message} Uploading and browsing still work; analysis and graph generation need the AI providers.</ErrorBox>;
  return null;
}

function Protected() {
  const { authEnabled, loading, session } = useAuth();
  const loc = useLocation();
  if (!authEnabled) return <Layout />;
  if (loading) return <p className="p-10 text-center font-hand text-3xl">Loading…</p>;
  if (!session) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  return <Layout />;
}

function Layout() {
  const { authEnabled, user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  return (
    <div className="flex min-h-full">
      <SketchDefs />
      <button className="fixed left-3 top-3 z-40 rounded-lg border-2 border-ink/70 bg-ivory p-2 md:hidden" onClick={() => setOpen(!open)} aria-label="Menu">
        {open ? <X size={18} /> : <Menu size={18} />}
      </button>
      <aside className={`fixed inset-y-0 left-0 z-30 w-60 shrink-0 bg-beige/95 p-4 backdrop-blur transition-transform md:static md:translate-x-0 ${open ? "" : "-translate-x-full"}`}>
        <div className="relative h-full overflow-hidden rounded-2xl border-2 border-ink/70 bg-ivory p-4" style={{ borderRadius: "20px 24px 18px 26px / 24px 18px 26px 20px" }}>
          <div className="mb-6 flex items-center gap-2">
            <Network className="shrink-0 text-forest" size={26} />
            <span className="font-display text-lg font-bold">ResearchGraph</span>
          </div>
          <nav className="space-y-1.5">
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <NavLink key={to} to={to} end={end} onClick={() => setOpen(false)}
                className={({ isActive }) => `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${isActive ? "bg-forest text-ivory" : "hover:bg-beige"}`}>
                <Icon size={18} /> {label}
              </NavLink>
            ))}
          </nav>
          {authEnabled && user && (
            <div className="mt-4 border-t border-sand pt-3">
              <p className="truncate px-3 text-xs text-ink/60" title={user.email}>{user.email}</p>
              <button onClick={signOut} className="mt-1 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition hover:bg-beige">
                <LogOut size={18} /> Sign out
              </button>
            </div>
          )}
          <Leaf className="absolute -bottom-2 left-1 h-28 w-20 opacity-90" />
          <Leaf className="absolute -bottom-2 right-0 h-20 w-14 opacity-80" flip />
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-4 py-5 pt-14 md:px-8 md:pt-6">
        <AiBanner />
        <Outlet />
      </main>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route element={<Protected />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/papers" element={<Papers />} />
        <Route path="/papers/:id" element={<PaperAnalysis />} />
        <Route path="/graph" element={<GraphPage />} />
        <Route path="/gaps" element={<Gaps />} />
        <Route path="/mentor" element={<Mentor />} />
        <Route path="*" element={<p className="font-hand text-3xl">Page not found.</p>} />
      </Route>
    </Routes>
  );
}
