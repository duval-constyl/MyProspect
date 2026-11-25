// Shapes of the backend API (backend/app/schemas.py and routers).

/** [west, south, east, north] in degrees. */
export type Bbox = [number, number, number, number];

export type LatLong = { lat: number; long: number };

export type ZoneKind = "commune" | "circle" | "polygon";

export type CollectBody = {
  kind: ZoneKind;
  geojson: Record<string, unknown>;
  naf_codes: string[];
};

export type JobState = "pending" | "running" | "done" | "failed";

export type Job = {
  state: JobState;
  done: number;
  total: number;
  error: string | null;
};

export type Cluster = {
  lat: number;
  long: number;
  count: number;
  max_score: number | null;
  tier: number | null;
  prospect_id: number | null;
};

export type Stats = {
  in_view: number;
  with_site: number;
  without_site: number;
};
