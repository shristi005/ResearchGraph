import axios from "axios";
import { authEnabled, supabase } from "./supabase";

export const API_URL = import.meta.env.VITE_API_BASE_URL ?? import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";
export const api = axios.create({ baseURL: API_URL, timeout: 0 }); // analysis/embedding calls can be slow

async function token() {
  if (!authEnabled) return null;
  const { data } = await supabase.auth.getSession(); // refreshes automatically when close to expiry
  return data.session?.access_token ?? null;
}

api.interceptors.request.use(async (config) => {
  const t = await token();
  if (t) config.headers.Authorization = `Bearer ${t}`;
  return config;
});

api.interceptors.response.use((r) => r, async (e) => {
  if (authEnabled && e?.response?.status === 401) console.error("401 from backend:", e.response.data?.detail, e.config?.url); // expired/invalid session -> back to login
  return Promise.reject(e);
});

// A plain <a href> cannot send the Authorization header, so the PDF is fetched with it and opened as a blob.
export async function openPaperPdf(id) {
  const w = window.open("", "_blank"); // opened synchronously so popup blockers allow it
  try {
    const r = await api.get(`/api/papers/${id}/file`, { responseType: "blob" });
    const url = URL.createObjectURL(new Blob([r.data], { type: "application/pdf" }));
    if (w) w.location.href = url; else window.location.href = url;
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (e) {
    if (w) w.close();
    throw e;
  }
}

export function errMsg(e) {
  if (e?.code === "ERR_NETWORK" || !e?.response) {
    return `Cannot reach the backend at ${API_URL}. If it is hosted on a free plan it may be waking up - wait ~30 seconds and retry.`;
  }
  const d = e.response.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x.msg).join("; ");
  return `Request failed (${e.response.status}).`;
}
