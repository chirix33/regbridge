import { useEffect, useRef, useState } from "react";
import { Upload, Folder } from "iconoir-react";
import { getProductDemoPackage } from "../api/client";
import { errorMessage } from "../api/wording";

export function DossierPicker({ file, onChange, label = "Dossier ZIP" }: { file: File | null; onChange: (file: File | null) => void; label?: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => () => { generation.current++; }, []);
  const select = (next: File | null) => { generation.current++; setBusy(false); setError(null); onChange(next); };
  async function sample() {
    const current = ++generation.current;
    setBusy(true); setError(null);
    try { const sampleFile = await getProductDemoPackage(); if (current === generation.current) { if (input.current) input.current.value = ""; onChange(sampleFile); } }
    catch (cause) { if (current === generation.current) setError(errorMessage(cause)); }
    finally { if (current === generation.current) setBusy(false); }
  }
  return <div className="dossier-picker">
    <p>Use a public, synthetic, or de-identified FDA/CDER dossier. One sequence in one ZIP; no confidential submissions.</p>
    <div className="upload-alternatives">
      <section className="upload-choice" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (e.dataTransfer.files.length !== 1) { setError("Choose one ZIP package at a time."); return; } select(e.dataTransfer.files[0]!); }}>
        <Upload aria-hidden="true"/><h2>Upload a dossier</h2><p>Drop one ZIP here or choose a file.</p>
        <input ref={input} aria-label={label} type="file" accept=".zip,application/zip" onChange={e => { const next = e.target.files?.[0]; if (next) select(next); }}/>
      </section>
      <span className="upload-or">or</span>
      <section className="upload-choice"><Folder aria-hidden="true"/><h2>Use a sample</h2><p>Explore a synthetic dossier through the same analysis process.</p><button type="button" disabled={busy} onClick={() => void sample()}>{busy ? "Loading sample…" : "Try a sample dossier"}</button></section>
    </div>
    {file && <div className="selected-dossier"><p>Selected: {file.name}</p><div><button type="button" onClick={() => input.current?.click()}>Change</button><button type="button" onClick={() => { select(null); if (input.current) input.current.value = ""; }}>Remove</button></div></div>}
    {busy && <button type="button" onClick={() => { generation.current++; setBusy(false); }}>Cancel sample loading</button>}
    {error && <p role="alert">{error}</p>}
  </div>;
}
