import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const key = import.meta.env.VITE_SUPABASE_ANON_KEY; // publishable/anon key only. NEVER put the service-role key in the frontend.

// When the variables are missing the app runs without login (matches a backend started with AUTH_DISABLED=true, local dev only).
export const authEnabled = Boolean(url && key);
export const supabase = authEnabled
  ? createClient(url, key, { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true } })
  : null;
