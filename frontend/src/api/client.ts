import type {
  AnalysisResult,
  ApplicationInventory,
  FixtureListResponse,
  GraphNeighborhood,
  DemoPresetsResponse,
  M4PresentationCasesResponse,
  M4PresentationResponse,
  MetadataPlan,
  ScenarioMode,
  ScopeResponse,
  StandardsSnapshotResponse,
  ModelCatalog,
  TargetContext,
  DossierAnalysisRun,
  ComparisonRun,
} from "./contracts";

const apiOrigin = import.meta.env.VITE_API_BASE_URL ?? "";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${apiOrigin}${path}`, {
    headers: { Accept: "application/json" },
  });
  return responseJson<T>(response);
}

async function responseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const messages: Record<number, string> = {
      404: "This dossier or result is no longer available. Upload the dossier again to start a new run.",
      413: "This ZIP is too large. Choose a smaller dossier package and try again.",
      415: "This file type isn't supported. Choose an eCTD dossier saved as a ZIP file.",
      422: "We couldn't validate this package or its options. Check the dossier and try again.",
      429: "RegBridge is handling too many requests. Wait a moment, then try again.",
      503: "The analysis service is unavailable. Check the model configuration or try again later.",
    };
    const message = messages[response.status] ?? (response.status >= 500
      ? "Something went wrong in the service. Please try again."
      : "We couldn't complete this request. Check your file and options, then try again.");
    const detail = typeof payload?.detail === "string" ? payload.detail : null;
    throw new Error(detail && response.status < 500 ? `${message} Details: ${detail}` : message);
  }
  return (await response.json()) as T;
}

export function getScope(): Promise<ScopeResponse> {
  return getJson<ScopeResponse>("/api/v1/config/scope");
}

export function getStandardsSnapshot(): Promise<StandardsSnapshotResponse> {
  return getJson<StandardsSnapshotResponse>("/api/v1/standards/snapshots");
}

export function getFixtures(): Promise<FixtureListResponse> {
  return getJson<FixtureListResponse>("/api/v1/fixtures");
}

export function getM3Presentation(): Promise<M4PresentationResponse> {
  return getJson<M4PresentationResponse>("/api/v1/presentation/m3");
}

export function getM3PresentationCases(): Promise<M4PresentationCasesResponse> {
  return getJson<M4PresentationCasesResponse>("/api/v1/presentation/m3/cases");
}

export function getDemoPresets(): Promise<DemoPresetsResponse> {
  return getJson<DemoPresetsResponse>("/api/v1/demo/presets");
}

export async function parseFixture(fixtureId: string): Promise<ApplicationInventory> {
  const response = await fetch(
    `${apiOrigin}/api/v1/applications/parse?fixture_id=${encodeURIComponent(fixtureId)}`,
    { method: "POST", headers: { Accept: "application/json" } },
  );
  return responseJson<ApplicationInventory>(response);
}

export function getModels(): Promise<ModelCatalog> {
  return getJson<ModelCatalog>("/api/v1/models");
}

export async function parseUpload(file: File): Promise<ApplicationInventory> {
  const response = await fetch(`${apiOrigin}/api/v1/applications/parse`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/zip" },
    body: file,
  });
  return responseJson<ApplicationInventory>(response);
}

export async function getProductDemoPackage(): Promise<File> {
  const response = await fetch(`${apiOrigin}/api/v1/product/demo-package`, {
    headers: { Accept: "application/zip" },
  });
  if (!response.ok) {
    await responseJson<never>(response);
  }
  return new File(
    [await response.blob()],
    "regbridge-m4-2-public-standards.zip",
    { type: "application/zip" },
  );
}

export async function createDossierAnalysis(
  inventoryId: string,
  modelId: string,
  targetContext: TargetContext,
  leafIds?: string[],
): Promise<DossierAnalysisRun> {
  const response = await fetch(`${apiOrigin}/api/v1/dossier-analyses`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ inventory_id: inventoryId, model_id: modelId, target_context: targetContext, leaf_ids: leafIds ?? null }),
  });
  return responseJson<DossierAnalysisRun>(response);
}

export function getDossierAnalysis(runId: string): Promise<DossierAnalysisRun> {
  return getJson<DossierAnalysisRun>(`/api/v1/dossier-analyses/${encodeURIComponent(runId)}`);
}

export async function createComparison(
  inventoryId: string,
  modelId: string,
  targetContext: TargetContext,
  leafIds?: string[],
): Promise<ComparisonRun> {
  const response = await fetch(`${apiOrigin}/api/v1/comparisons`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ inventory_id: inventoryId, model_id: modelId, target_context: targetContext, leaf_ids: leafIds ?? null }),
  });
  return responseJson<ComparisonRun>(response);
}

export function getComparison(comparisonId: string): Promise<ComparisonRun> {
  return getJson<ComparisonRun>(`/api/v1/comparisons/${encodeURIComponent(comparisonId)}`);
}

export async function createAnalysis(
  inventoryId: string,
  leafId: string,
  scenarioMode: ScenarioMode,
  metadataPlan: MetadataPlan | null = null,
): Promise<AnalysisResult> {
  const response = await fetch(`${apiOrigin}/api/v1/analyses`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({
      inventory_id: inventoryId,
      leaf_id: leafId,
      target_context: {
        authority: "FDA",
        center: "CDER",
        application_type: "NDA",
        source_standard: "eCTD-3.2.2",
        target_standard: "eCTD-4.0",
        analysis_date: new Date().toISOString().slice(0, 10),
        reuse_operation: "reference-existing-content",
        standards_snapshot_id: "fda-cder-demo-v1",
        scenario_mode: scenarioMode,
        metadata_plan: metadataPlan,
      },
    }),
  });
  const payload = await responseJson<{ analysis: AnalysisResult }>(response);
  return payload.analysis;
}

export async function getAnalysisGraph(analysisId: string): Promise<GraphNeighborhood> {
  const payload = await getJson<{ graph: GraphNeighborhood }>(
    `/api/v1/analyses/${encodeURIComponent(analysisId)}/graph`,
  );
  return payload.graph;
}
