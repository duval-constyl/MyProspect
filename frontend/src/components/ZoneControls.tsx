import { type FormEvent, useState } from "react";

import type { CollectBody, LatLong, ZoneKind } from "../types";

export const TRADES = [
  { label: "Garage", naf: "45.20A" },
  { label: "Coiffure", naf: "96.02A" },
  { label: "Restauration", naf: "56.10A" },
  { label: "Plomberie", naf: "43.22A" },
  { label: "Agence immobilière", naf: "68.31Z" },
] as const;

const TABS: { kind: ZoneKind; label: string }[] = [
  { kind: "commune", label: "Commune" },
  { kind: "circle", label: "Cercle" },
  { kind: "polygon", label: "Dessin libre" },
];

type Props = {
  onCollect: (body: CollectBody) => void;
  /** Centre of the map, used as the centre of a circle zone. */
  mapCenter?: LatLong | null;
  /** Vertices [long, lat] placed on the map in « Dessin libre ». */
  drawnPoints?: [number, number][];
  onKindChange?: (kind: ZoneKind) => void;
  onClearDrawing?: () => void;
  busy?: boolean;
};

export default function ZoneControls({
  onCollect,
  mapCenter = null,
  drawnPoints = [],
  onKindChange,
  onClearDrawing,
  busy = false,
}: Props) {
  const [kind, setKind] = useState<ZoneKind>("commune");
  const [commune, setCommune] = useState("");
  const [radiusKm, setRadiusKm] = useState("2");
  const [trades, setTrades] = useState<string[]>([]);
  const [problem, setProblem] = useState<string | null>(null);

  function selectKind(next: ZoneKind) {
    setKind(next);
    setProblem(null);
    onKindChange?.(next);
  }

  function toggleTrade(naf: string) {
    setTrades((current) => (current.includes(naf) ? current.filter((c) => c !== naf) : [...current, naf]));
  }

  function zoneGeojson(): Record<string, unknown> | string {
    if (kind === "commune") {
      return commune.trim() ? { commune: commune.trim() } : "Indiquez une commune.";
    }
    if (kind === "circle") {
      const radius = Number(radiusKm.replace(",", "."));
      if (!mapCenter) return "La carte n'est pas encore prête.";
      if (!(radius > 0 && radius <= 50)) return "Le rayon doit être compris entre 0 et 50 km.";
      return {
        type: "Feature",
        geometry: { type: "Point", coordinates: [mapCenter.long, mapCenter.lat] },
        properties: { radius_km: radius },
      };
    }
    if (drawnPoints.length < 3) return "Placez au moins trois points sur la carte.";
    return { type: "Polygon", coordinates: [[...drawnPoints, drawnPoints[0]]] };
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const geojson = zoneGeojson();
    if (typeof geojson === "string") return setProblem(geojson);
    if (trades.length === 0) return setProblem("Choisissez au moins un métier.");
    setProblem(null);
    // Codes in the order of the list, whatever the click order.
    const naf_codes = TRADES.map((t) => t.naf).filter((naf) => trades.includes(naf));
    onCollect({ kind, geojson, naf_codes });
  }

  return (
    <form className="zone-controls" onSubmit={submit}>
      <h2>Nouvelle récolte</h2>
      <div role="tablist" className="tabs">
        {TABS.map((tab) => (
          <button
            key={tab.kind}
            type="button"
            role="tab"
            aria-selected={kind === tab.kind}
            className={kind === tab.kind ? "tab active" : "tab"}
            onClick={() => selectKind(tab.kind)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {kind === "commune" && (
        <label className="field">
          Commune (nom ou code INSEE)
          <input value={commune} onChange={(e) => setCommune(e.target.value)} placeholder="Villeurbanne" />
        </label>
      )}
      {kind === "circle" && (
        <>
          <label className="field">
            Rayon (km)
            <input type="number" min="0.5" max="50" step="0.5" value={radiusKm} onChange={(e) => setRadiusKm(e.target.value)} />
          </label>
          <p className="hint">Centre : le centre actuel de la carte.</p>
        </>
      )}
      {kind === "polygon" && (
        <>
          <p className="hint">
            Cliquez sur la carte pour placer les sommets ({drawnPoints.length} point
            {drawnPoints.length > 1 ? "s" : ""}).
          </p>
          <button type="button" className="secondary" onClick={onClearDrawing}>
            Effacer le dessin
          </button>
        </>
      )}

      <fieldset className="trades">
        <legend>Métiers</legend>
        {TRADES.map((trade) => (
          <label key={trade.naf} className="check">
            <input type="checkbox" checked={trades.includes(trade.naf)} onChange={() => toggleTrade(trade.naf)} />
            {`${trade.label} (${trade.naf})`}
          </label>
        ))}
      </fieldset>

      {problem && (
        <p role="alert" className="error">
          {problem}
        </p>
      )}
      <button type="submit" className="primary" disabled={busy}>
        Lancer la récolte
      </button>
    </form>
  );
}
