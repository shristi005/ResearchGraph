import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Network } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { Leaf, SketchDefs } from "../components/Doodles";
import { Button, Card, ErrorBox } from "../components/ui";

const INPUT = "w-full rounded-xl border-2 border-ink/70 bg-ivory px-3 py-2 text-sm outline-none focus:border-forest";

function Shell({ title, subtitle, children, footer }) {
  return (
    <div className="relative flex min-h-full items-center justify-center overflow-hidden px-4 py-10">
      <SketchDefs />
      <Leaf className="absolute -bottom-2 left-2 hidden h-44 w-32 opacity-90 md:block" />
      <Leaf className="absolute -bottom-2 right-2 hidden h-36 w-24 opacity-80 md:block" flip />
      <div className="w-full max-w-md">
        <div className="mb-4 flex items-center justify-center gap-2">
          <Network className="text-forest" size={28} />
          <span className="font-display text-2xl font-bold">ResearchGraph</span>
        </div>
        <Card className="rise">
          <h1 className="font-display text-2xl font-semibold">{title}</h1>
          {subtitle && <p className="mt-1 font-hand text-2xl text-forest">{subtitle}</p>}
          <div className="mt-4">{children}</div>
        </Card>
        {footer && <p className="mt-4 text-center text-sm text-ink/70">{footer}</p>}
      </div>
    </div>
  );
}

function Field({ label, ...p }) {
  return (
    <label className="mb-3 block text-sm font-medium">
      {label}
      <input className={`mt-1 ${INPUT}`} {...p} />
    </label>
  );
}

const msg = (e) => (e?.message?.includes("Invalid login") ? "Email or password is incorrect." : e?.message || "Something went wrong. Please try again.");

export function Login() {
  const { signIn, session } = useAuth();
  const nav = useNavigate();
  const from = useLocation().state?.from || "/";
  const [email, setEmail] = useState(""); const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  if (session) return <Navigate to={from} replace />;
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError("");
    const { error } = await signIn(email.trim(), password);
    setBusy(false);
    if (error) setError(msg(error)); else nav(from, { replace: true });
  };
  return (
    <Shell title="Welcome back" subtitle="sign in to your papers"
      footer={<>New here? <Link className="font-semibold text-forest underline" to="/signup">Create an account</Link></>}>
      <form onSubmit={submit}>
        <ErrorBox className="mb-3">{error}</ErrorBox>
        <Field label="Email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <Field label="Password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        <div className="mb-4 text-right text-sm"><Link className="text-forest underline" to="/forgot-password">Forgot password?</Link></div>
        <Button type="submit" loading={busy} className="w-full justify-center">Sign in</Button>
      </form>
    </Shell>
  );
}

export function Signup() {
  const { signUp, session } = useAuth();
  const [name, setName] = useState(""); const [email, setEmail] = useState(""); const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [sent, setSent] = useState(false);
  if (session) return <Navigate to="/" replace />;
  const submit = async (e) => {
    e.preventDefault(); setError("");
    if (password.length < 8) return setError("Use at least 8 characters for your password.");
    setBusy(true);
    const { data, error } = await signUp(email.trim(), password, name.trim());
    setBusy(false);
    if (error) return setError(msg(error));
    if (!data.session) setSent(true); // email confirmation is on: the user must click the link first
  };
  return (
    <Shell title="Create your account" subtitle="your own private paper shelf"
      footer={<>Already registered? <Link className="font-semibold text-forest underline" to="/login">Sign in</Link></>}>
      {sent ? (
        <p className="text-sm">We sent a confirmation link to <b>{email}</b>. Open it, then <Link className="font-semibold text-forest underline" to="/login">sign in</Link>.</p>
      ) : (
        <form onSubmit={submit}>
          <ErrorBox className="mb-3">{error}</ErrorBox>
          <Field label="Name (optional)" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
          <Field label="Email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <Field label="Password" type="password" autoComplete="new-password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} />
          <Button type="submit" loading={busy} className="w-full justify-center">Sign up</Button>
        </form>
      )}
    </Shell>
  );
}

export function ForgotPassword() {
  const { sendReset } = useAuth();
  const [email, setEmail] = useState(""); const [busy, setBusy] = useState(false);
  const [error, setError] = useState(""); const [sent, setSent] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError("");
    const { error } = await sendReset(email.trim());
    setBusy(false);
    if (error) setError(msg(error)); else setSent(true);
  };
  return (
    <Shell title="Reset your password" subtitle="we'll email you a link"
      footer={<Link className="font-semibold text-forest underline" to="/login">Back to sign in</Link>}>
      {sent ? <p className="text-sm">If an account exists for <b>{email}</b>, a reset link is on its way.</p> : (
        <form onSubmit={submit}>
          <ErrorBox className="mb-3">{error}</ErrorBox>
          <Field label="Email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <Button type="submit" loading={busy} className="w-full justify-center">Send reset link</Button>
        </form>
      )}
    </Shell>
  );
}

export function ResetPassword() {
  const { updatePassword, recovery, session, loading } = useAuth();
  const nav = useNavigate();
  const [password, setPassword] = useState(""); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  if (!loading && !recovery && !session) return <Navigate to="/forgot-password" replace />;
  const submit = async (e) => {
    e.preventDefault(); setError("");
    if (password.length < 8) return setError("Use at least 8 characters for your password.");
    setBusy(true);
    const { error } = await updatePassword(password);
    setBusy(false);
    if (error) setError(msg(error)); else nav("/", { replace: true });
  };
  return (
    <Shell title="Choose a new password" subtitle="almost done">
      <form onSubmit={submit}>
        <ErrorBox className="mb-3">{error}</ErrorBox>
        <Field label="New password" type="password" autoComplete="new-password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} />
        <Button type="submit" loading={busy} className="w-full justify-center">Update password</Button>
      </form>
    </Shell>
  );
}
