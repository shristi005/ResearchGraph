import { useRef, useState } from "react";
import { CheckCircle2, CopyX, FileUp, XCircle } from "lucide-react";
import { api, errMsg } from "../api";
import { Button, ErrorBox } from "./ui";

const ICON = { created: <CheckCircle2 size={16} className="text-forest" />, duplicate: <CopyX size={16} className="text-mustard" />, rejected: <XCircle size={16} className="text-terracotta" /> };

export default function UploadZone({ onUploaded }) {
  const input = useRef(null);
  const [drag, setDrag] = useState(false);
  const [queue, setQueue] = useState([]);
  const [progress, setProgress] = useState(null);
  const [results, setResults] = useState([]);
  const [error, setError] = useState("");

  const addFiles = (list) => {
    const files = [...list];
    const bad = files.filter((f) => !f.name.toLowerCase().endsWith(".pdf"));
    if (bad.length) setError(`Not a PDF, skipped: ${bad.map((f) => f.name).join(", ")}`);
    else setError("");
    setQueue((q) => [...q, ...files.filter((f) => f.name.toLowerCase().endsWith(".pdf"))]);
  };

  const upload = async () => {
    const fd = new FormData();
    queue.forEach((f) => fd.append("files", f));
    setError(""); setResults([]); setProgress(0);
    try {
      const { data } = await api.post("/api/papers/upload", fd, {
        onUploadProgress: (e) => e.total && setProgress(Math.round((e.loaded / e.total) * 100)),
      });
      setResults(data.results);
      setQueue([]);
      onUploaded?.();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setProgress(null);
    }
  };

  return (
    <div>
      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files); }}
        className={`sketch flex cursor-pointer flex-col items-center gap-2 border-dashed px-6 py-10 text-center transition ${drag ? "scale-[1.01] !bg-sage/40" : ""}`}
        onClick={() => input.current?.click()}
        role="button" tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && input.current?.click()}
      >
        <FileUp size={38} className={drag ? "bob text-forest" : "text-forest"} />
        <p className="font-hand text-3xl">Drag &amp; drop PDF files here</p>
        <p className="text-sm text-ink/70">or click to browse · PDF only · up to 25 MB each</p>
        <input ref={input} type="file" accept="application/pdf,.pdf" multiple hidden onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
      </div>

      {queue.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {queue.map((f, i) => (
            <span key={f.name + i} className="flex items-center gap-1 rounded-full border border-ink/30 bg-beige px-3 py-1 text-xs">
              {f.name}
              <button aria-label={`Remove ${f.name}`} onClick={() => setQueue(queue.filter((_, j) => j !== i))}>×</button>
            </span>
          ))}
          <Button onClick={upload} loading={progress !== null} className="ml-auto">
            {progress !== null ? `Uploading ${progress}%` : `Upload ${queue.length} file${queue.length > 1 ? "s" : ""}`}
          </Button>
        </div>
      )}
      {progress !== null && (
        <div className="mt-2 h-2.5 overflow-hidden rounded-full border border-ink/40 bg-beige">
          <div className="h-full bg-forest transition-all" style={{ width: `${progress}%` }} />
        </div>
      )}
      <ErrorBox className="mt-3">{error}</ErrorBox>
      {results.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm">
          {results.map((r, i) => (
            <li key={i} className="flex items-start gap-2">{ICON[r.outcome]}<span><b>{r.filename}</b>: {r.message}</span></li>
          ))}
        </ul>
      )}
    </div>
  );
}
