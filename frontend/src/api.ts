import type { Bbox, Cluster, CollectBody, Job, Stats } from "./types";

// Vite forwards /api to the backend (see vite.config.ts).
const BASE = "/api";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, "Serveur injoignable : vérifiez que l'API est lancée.");
  }
  if (!response.ok) {
    let message = `Erreur ${response.status}`;
    try {
      const data = await response.json();
      if (typeof data?.detail === "string") message = data.detail;
    } catch {
      // keep the generic message
    }
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  collectZone: (body: CollectBody) =>
    request<{ job_id: number }>("/zones/collect", { method: "POST", body: JSON.stringify(body) }),
  getJob: (id: number) => request<Job>(`/jobs/${id}`),
  getClusters: (bbox: Bbox, zoom: number) =>
    request<{ clusters: Cluster[] }>(
      `/prospects/clusters?bbox=${bbox.join(",")}&zoom=${Math.max(0, Math.floor(zoom))}`,
    ),
  getStats: (bbox: Bbox) => request<Stats>(`/prospects/stats?bbox=${bbox.join(",")}`),
};
