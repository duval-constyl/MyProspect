import type { Status } from "./types";

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
