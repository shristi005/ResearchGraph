import { useCallback, useEffect, useRef, useState } from "react";
import { api, errMsg } from "./api";

/** Loads the paper list and re-polls every 2s while any paper is being analyzed. */
export function usePapers() {
  const [papers, setPapers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const timer = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get("/api/papers");
      setPapers(data);
      setError("");
      clearTimeout(timer.current);
      if (data.some((p) => p.status === "analyzing")) timer.current = setTimeout(refresh, 2000);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    return () => clearTimeout(timer.current);
  }, [refresh]);

  return { papers, loading, error, refresh };
}
