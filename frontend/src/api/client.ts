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
} from "./contracts";

const apiOrigin = import.meta.env.VITE_API_BASE_URL ?? "";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${apiOrigin}${path}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`RegBridge API request failed with status ${response.status}`);
  }
  return (await response.json()) as T;
}

async function responseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const detail = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detail?.detail ?? `RegBridge API request failed with status ${response.status}`);
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
