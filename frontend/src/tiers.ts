/** Colour per opportunity tier (1 = low, 6 = high), shared by the map, the list and the card. */
export const TIER_COLORS = ["#8d99ae", "#4f7cac", "#2a9d8f", "#e9c46a", "#f4a261", "#d62828"];
export const NO_SCORE_COLOR = "#b0b0b0";

export function tierColor(tier: number | null | undefined): string {
  return tier && tier >= 1 && tier <= 6 ? TIER_COLORS[tier - 1] : NO_SCORE_COLOR;
}
