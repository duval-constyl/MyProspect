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

export type Offer = "web" | "mobile" | "cloud";

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
  score: number | null; // score of the selected offer
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
  offer: Offer;
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

export type Reason = { code: string; label: string; points: number };

export type Priority = { value: number; reasons: Reason[] };

export type Score = { offer: string; value: number; tier: number; reasons: Reason[] };

export type ContactKind = "phone" | "email" | "website";

export type Contact = { kind: ContactKind; value: string; source: string; seen_on: string };

export type SiteAnalysis = {
  url: string;
  reachable: boolean;
  https: boolean;
  has_title: boolean;
  has_description: boolean;
  has_h1: boolean;
  has_viewport: boolean;
  response_ms: number | null;
  tech: string[];
  mobile_perf: number | null;
  analyzed_at: string;
};

export type Tracking = { status: Status; favorite: boolean; notes: string; updated_at: string | null };

export type FollowUp = { id: number; prospect_id: number; due_on: string; note: string; done_at: string | null };

export type FollowUpDue = {
  id: number;
  prospect_id: number;
  prospect_name: string;
  phone: string | null;
  due_on: string;
  note: string;
};

export type TopProspect = {
  id: number;
  name: string;
  city: string | null;
  phone: string | null;
  best_offer: Offer;
  score: number | null;
  priority: number;
  status: Status;
};

export type TodayData = { followups_due: FollowUpDue[]; top_priority: TopProspect[] };

export type TrackingEvent = { at: string; kind: "status" | "note" | "followup"; text: string };

export type HistoryData = { followups: FollowUp[]; events: TrackingEvent[] };

export type Channel = "email" | "call";

/** An outreach draft: never sent by the tool. */
export type Draft = {
  id: number;
  offer: Offer;
  channel: Channel;
  subject: string | null;
  body: string;
  source: "llm" | "template";
  variant: string;
  created_at: string;
};

export type TrackingPatch =Partial<Pick<Tracking, "status" | "favorite" | "notes">>;

export type ProspectDetail = {
  id: number;
  siret: string;
  name: string;
  naf: string;
  effectif_code: string | null;
  created_on: string | null;
  address: string;
  city: string | null;
  lat: number | null;
  long: number | null;
  is_individual: boolean;
  opposed_to_prospecting: boolean;
  first_seen_at: string;
  last_collected_at: string;
  contacts: Contact[];
  site_analysis: SiteAnalysis | null;
  scores: Score[];
  priority: Priority;
  priority_by_offer: Partial<Record<Offer, Priority>>;
  tracking: Tracking;
};

/** A collected zone; watched zones are collected again every `watch_every_days` days. */
export type ZoneInfo = {
  id: number;
  kind: ZoneKind;
  label: string;
  geojson: unknown;
  naf_codes: string[];
  collected_at: string;
  watch: boolean;
  watch_every_days: number;
  last_watch_at: string | null;
};

export type ZonePatch = Partial<Pick<ZoneInfo, "watch" | "watch_every_days">>;

export type AlertKind = "new_company" | "closed";

export type Alert = {
  id: number;
  kind: AlertKind;
  zone_id: number;
  zone_label: string;
  prospect_id: number;
  prospect_name: string;
  created_at: string;
  seen_at: string | null;
};

export type ProspectRef = { id: number; name: string };

export type DuplicatePair = { first: ProspectRef; second: ProspectRef };
