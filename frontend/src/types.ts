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

export type Status = "new" | "to_contact" | "contacted" | "replied" | "refused";

export type ProspectListItem = {
  id: number;
  siret: string;
  name: string;
  naf: string;
  address: string;
  city: string | null;
  lat: number | null;
  long: number | null;
  score_web: number | null;
  tier: number | null;
  priority: number;
  status: Status;
  favorite: boolean;
  has_site: boolean;
  phone: string | null;
  email: string | null;
  website: string | null;
  opposed_to_prospecting: boolean;
};

export type ProspectList = { items: ProspectListItem[]; total: number };

export type SortKey = "priority" | "score" | "name";
export type SortOrder = "asc" | "desc";

/** Filters of GET /prospects, shared with the CSV export. */
export type ProspectFilters = {
  naf?: string;
  has_site?: boolean;
  score_min?: number;
  status?: Status;
  favorite?: boolean;
  opposed?: boolean;
  q?: string;
  sort: SortKey;
  order: SortOrder;
};
