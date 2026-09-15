import type { TargetContext } from "./contracts";

export function defaultTarget(): TargetContext {
  return { authority: "FDA", center: "CDER", application_type: "NDA", source_standard: "eCTD-3.2.2", target_standard: "eCTD-4.0", analysis_date: new Date().toISOString().slice(0, 10), reuse_operation: "reference-existing-content", standards_snapshot_id: "fda-cder-demo-v1", scenario_mode: "prospective_forward_compatibility", metadata_plan: { intent: "unspecified", manufacturer_partitioning: "unknown", replacement_manufacturer_value: null } };
}
export function savedTarget(inventoryId?: string): TargetContext {
  try {
    const saved = JSON.parse(sessionStorage.getItem("regbridge.target") ?? "null") as { inventoryId: string; context: TargetContext } | null;
    const c = saved?.context;
    if (saved?.inventoryId === inventoryId && c?.authority === "FDA" && c.center === "CDER" && c.application_type === "NDA" && c.source_standard === "eCTD-3.2.2" && c.target_standard === "eCTD-4.0" && c.standards_snapshot_id === "fda-cder-demo-v1" && ["prospective_forward_compatibility", "current_operational"].includes(c.scenario_mode) && ["unspecified", "normalize-metadata", "preserve-existing-lifecycle"].includes(c.metadata_plan?.intent)) return c;
  } catch { /* Unavailable context requires explicit setup; no preservation default. */ }
  return defaultTarget();
}
