import type { AlertKind, ContactKind, Offer, Status } from "./types";

/** Starting list of trades (V1 plan, Task 12). */
export const TRADES = [
  { label: "Garage", naf: "45.20A" },
  { label: "Coiffure", naf: "96.02A" },
  { label: "Restauration", naf: "56.10A" },
  { label: "Plomberie", naf: "43.22A" },
  { label: "Agence immobilière", naf: "68.31Z" },
] as const;

export function tradeLabel(naf: string): string {
  return TRADES.find((trade) => trade.naf === naf)?.label ?? naf;
}

export const STATUS_LABELS: Record<Status, string> = {
  new: "Nouveau",
  to_contact: "À contacter",
  contacted: "Contacté",
  replied: "A répondu",
  refused: "Refusé",
};

/** What is shown for an absent value: never empty, never "null". */
export const MISSING = "—";

export const CONTACT_KIND_LABELS: Record<ContactKind, string> = {
  phone: "Téléphone",
  email: "E-mail",
  website: "Site web",
};

export const SOURCE_LABELS: Record<string, string> = {
  osm: "OpenStreetMap",
  registry: "Registre officiel",
  site: "Site web de l'entreprise",
};

/** The three offers, in display order. */
export const OFFERS: { value: Offer; label: string }[] = [
  { value: "web", label: "Web" },
  { value: "mobile", label: "Mobile" },
  { value: "cloud", label: "Cloud et logiciel" },
];

export function offerLabel(offer: string): string {
  return OFFERS.find((o) => o.value === offer)?.label ?? offer;
}

export const OFFER_LABELS: Record<string, string> = {
  web: "Score Web",
  mobile: "Score Mobile",
  cloud: "Score Cloud et logiciel",
};

/** Timestamp (UTC ISO) -> its Paris calendar day, "25/11/2026". */
export function parisDate(isoDateTime: string | null | undefined): string {
  if (!isoDateTime) return MISSING;
  return new Intl.DateTimeFormat("fr-FR", { timeZone: "Europe/Paris" }).format(new Date(isoDateTime));
}

/** "2026-11-20" -> "20/11/2026" (no time zone shift). */
export function frenchDate(isoDate: string | null | undefined): string {
  if (!isoDate) return MISSING;
  const [year, month, day] = isoDate.slice(0, 10).split("-");
  return `${day}/${month}/${year}`;
}

export const ALERT_KIND_LABELS: Record<AlertKind, string> = {
  new_company: "Nouvelle entreprise",
  closed: "Entreprise fermée",
};

/** How often a watched zone is collected again (days). */
export const WATCH_FREQUENCIES = [
  { days: 1, label: "Chaque jour" },
  { days: 7, label: "Chaque semaine" },
  { days: 14, label: "Toutes les 2 semaines" },
  { days: 30, label: "Chaque mois" },
];

/** "template:v1" -> "Modèle de texte fixe (v1)", "llm:<modèle>:v1" -> "Rédigé par l'IA (<modèle>, v1)". */
export function variantLabel(variant: string): string {
  const [kind, ...rest] = variant.split(":");
  if (kind === "template") return `Modèle de texte fixe (${rest.join(":") || "v1"})`;
  if (kind === "llm") return `Rédigé par l'IA (${rest.join(", ")})`;
  return variant;
}

const PERCENT = new Intl.NumberFormat("fr-FR", { style: "percent", maximumFractionDigits: 0 });

/** 0.25 -> "25 %". */
export function percent(rate: number): string {
  return PERCENT.format(rate);
}
