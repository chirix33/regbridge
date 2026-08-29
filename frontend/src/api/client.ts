import type { ScopeResponse, StandardsSnapshotResponse } from "./contracts";

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

export function getScope(): Promise<ScopeResponse> {
  return getJson<ScopeResponse>("/api/v1/config/scope");
}

export function getStandardsSnapshot(): Promise<StandardsSnapshotResponse> {
  return getJson<StandardsSnapshotResponse>("/api/v1/standards/snapshots");
}

