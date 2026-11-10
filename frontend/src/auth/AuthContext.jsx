import { createContext, useContext, useEffect, useState } from "react";
import { authEnabled, supabase } from "../supabase";

const Ctx = createContext(null);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(authEnabled);
  const [recovery, setRecovery] = useState(false); // true after the user opens a password-reset email link

  useEffect(() => {
    if (!authEnabled) return;
    let alive = true;
    supabase.auth.getSession().then(({ data }) => { if (alive) { setSession(data.session); setLoading(false); } });
    const { data: sub } = supabase.auth.onAuthStateChange((event, s) => {
      setSession(s);
      if (event === "PASSWORD_RECOVERY") setRecovery(true);
      if (event === "SIGNED_OUT") setRecovery(false);
    });
    return () => { alive = false; sub.subscription.unsubscribe(); };
  }, []);

  const value = {
    authEnabled, loading, session, recovery, user: session?.user ?? null,
    signIn: (email, password) => supabase.auth.signInWithPassword({ email, password }),
    signUp: (email, password, displayName) =>
      supabase.auth.signUp({ email, password, options: { data: { display_name: displayName || undefined }, emailRedirectTo: window.location.origin } }),
    signOut: () => supabase.auth.signOut(),
    sendReset: (email) => supabase.auth.resetPasswordForEmail(email, { redirectTo: `${window.location.origin}/reset-password` }),
    updatePassword: async (password) => { const r = await supabase.auth.updateUser({ password }); if (!r.error) setRecovery(false); return r; },
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
