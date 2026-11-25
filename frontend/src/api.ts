import type {
  Bbox,
  Cluster,
  CollectBody,
  Job,
  Offer,
  ProspectDetail,
  ProspectFilters,
  ProspectList,
  Stats,
  Tracking,
  TrackingPatch,
} from "./types";

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

/** Query string of the list filters; absent values are left out. */
export function filtersQuery(filters: ProspectFilters, extra: Record<string, number> = {}): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries({ ...filters, ...extra })) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  return params.toString();
}

export const api = {
  collectZone: (body: CollectBody) =>
    request<{ job_id: number }>("/zones/collect", { method: "POST", body: JSON.stringify(body) }),
  getJob: (id: number) => request<Job>(`/jobs/${id}`),
  getClusters: (bbox: Bbox, zoom: number, offer: Offer = "web") =>
    request<{ clusters: Cluster[] }>(
      `/prospects/clusters?bbox=${bbox.join(",")}&zoom=${Math.max(0, Math.floor(zoom))}&offer=${offer}`,
    ),
  getStats: (bbox: Bbox) => request<Stats>(`/prospects/stats?bbox=${bbox.join(",")}`),
  listProspects: (filters: ProspectFilters, page: number, perPage: number) =>
    request<ProspectList>(`/prospects?${filtersQuery(filters, { page, per_page: perPage })}`),
  /** Plain link (the browser downloads the file), same filters as the list. */
  exportUrl: (filters: ProspectFilters) => `${BASE}/exports/prospects.csv?${filtersQuery(filters)}`,
  getProspect: (id: number) => request<ProspectDetail>(`/prospects/${id}`),
  patchTracking: (id: number, patch: TrackingPatch) =>
    request<Tracking>(`/prospects/${id}/tracking`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteProspect: (id: number) => request<void>(`/prospects/${id}`, { method: "DELETE" }),
  doNotContact: (id: number) => request<Tracking>(`/prospects/${id}/do-not-contact`, { method: "POST" }),
};
