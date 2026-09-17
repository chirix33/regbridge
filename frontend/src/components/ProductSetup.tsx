import { useEffect, useId, useRef, useState } from "react";
import { HelpCircle } from "iconoir-react";
import type { ActiveProductConfiguration, TargetContext } from "../api/contracts";

const choices = [
  { value: "preserve-existing-lifecycle", label: "Preserve existing metadata", help: "Evaluate reuse with the existing lifecycle and exact context metadata. Recorded qualifications still apply; this does not guarantee reuse eligibility." },
  { value: "normalize-metadata", label: "Plan metadata changes", help: "Evaluate changes for the target context. A new context group, suspension of the old context, or manufacturer partitioning may need review and approval. RegBridge does not perform these changes." },
  { value: "unspecified", label: "I’m not sure yet", help: "Leave migration intent unresolved. RegBridge will retain any supported recommendation and identify where intent must be confirmed before deciding reuse." },
] as const;
function IntentHelp({ label, children }: { label: string; children: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const outside = (e: PointerEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const escape = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); } };
    document.addEventListener("pointerdown", outside); document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape); };
  }, [open]);
  return <span ref={ref} className="intent-help" onPointerEnter={e => { if (e.pointerType === "mouse") setOpen(true); }} onPointerLeave={e => { if (e.pointerType === "mouse") setOpen(false); }} onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false); }}>
    <button type="button" className="icon-button" aria-label={`About ${label.toLowerCase()}`} aria-expanded={open} aria-controls={id} aria-describedby={open ? id : undefined} onFocus={() => setOpen(true)} onClick={() => setOpen(true)}><HelpCircle aria-hidden="true"/></button>
    {open && <span id={id} role="note" className="help-popover">{children}</span>}
  </span>;
}
export function ProductSetup({ value, onChange }: { value: TargetContext; onChange: (value: TargetContext) => void }) {
  const name = useId();
  return <section className="product-setup">
    <p className="setup-intro">We’ll compare your <strong>eCTD v3.2.2</strong> dossier with the selected <strong>eCTD v4.0</strong> requirements to identify reuse decisions.</p>
    <p className="field-note">Selected FDA/CDER Module 3 checks · prospective research scenario.</p>
    <fieldset><legend>How should metadata be handled?</legend>
      {choices.map(choice => <div className="intent-choice" key={choice.value}>
        <label><input type="radio" name={name} value={choice.value} checked={value.metadata_plan.intent === choice.value} onChange={() => onChange({ ...value, scenario_mode: "prospective_forward_compatibility", metadata_plan: { ...value.metadata_plan, intent: choice.value } })}/>{choice.label}</label>
        <IntentHelp label={choice.label}>{choice.help}</IntentHelp>
      </div>)}
      <p className="field-note">Effective intent: {choices.find(c => c.value === value.metadata_plan.intent)?.label}. Manufacturer grouping: {value.metadata_plan.manufacturer_partitioning}.</p>
    </fieldset>
  </section>;
}
export function ConfigurationDisclosure({ config }: { config: ActiveProductConfiguration }) {
  const text = { not_transmitted: "Offline demonstration. Evidence is not transmitted; no live AI call is made.", external_provider: "Document evidence will be sent to the configured external provider.", local_service: "Document evidence will be sent to the configured local service.", unavailable: "Analysis is unavailable. Contact the service operator to correct the configuration." };
  return <p className="configuration-disclosure" role={config.availability === "available" ? undefined : "alert"}>{text[config.availability === "available" ? config.evidence_transmission : "unavailable"]}{config.availability !== "available" && <span> {config.detail}</span>}</p>;
}
