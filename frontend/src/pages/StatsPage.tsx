import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api";
import { STATUS_LABELS, offerLabel, percent, variantLabel } from "../labels";
import type { StatsGroupBy } from "../types";

const GROUPS: { value: StatsGroupBy; label: string; column: string; none: string }[] = [
  { value: "offer", label: "Offre", column: "Offre", none: "Sans brouillon" },
  { value: "variant", label: "Variante du brouillon", column: "Variante", none: "Sans brouillon" },
  { value: "zone", label: "Zone", column: "Zone", none: "Hors zone" },
];

/** « Statistiques » : reply rate of the outreach, per offer, draft variant or zone. */
export default function StatsPage() {
  const [groupBy, setGroupBy] = useState<StatsGroupBy>("offer");
  const group = GROUPS.find((item) => item.value === groupBy)!;
  const stats = useQuery({ queryKey: ["stats", "outreach", groupBy], queryFn: () => api.getOutreachStats(groupBy) });
  const zones = useQuery({ queryKey: ["zones"], queryFn: api.listZones, enabled: groupBy === "zone" });

  function keyLabel(key: string): string {
    if (key === "none") return group.none;
    if (groupBy === "offer") return offerLabel(key);
    if (groupBy === "variant") return variantLabel(key);
    return zones.data?.find((zone) => String(zone.id) === key)?.label ?? `Zone n° ${key}`;
  }

  return (
    <div className="alerts-page">
      <section className="card" aria-label="Statistiques">
        <h2>Statistiques de réponse</h2>
        <p className="hint">
          Un prospect compte comme contacté dès que son statut est « {STATUS_LABELS.contacted} », «{" "}
          {STATUS_LABELS.replied} » ou « {STATUS_LABELS.refused} ». Son offre et sa variante sont celles de son dernier
          brouillon.
        </p>
        <label>
          Regrouper par{" "}
          <select value={groupBy} onChange={(event) => setGroupBy(event.target.value as StatsGroupBy)}>
            {GROUPS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        {stats.isError ? (
          <p role="alert" className="error">
            {stats.error.message}
          </p>
        ) : !stats.data ? (
          <p className="hint">Chargement…</p>
        ) : stats.data.length === 0 ? (
          <p className="hint">
            Aucun prospect contacté pour l'instant : préparez un brouillon depuis une fiche, puis changez son statut une fois le
            message envoyé.
          </p>
        ) : (
          <table className="prospects" aria-label="Statistiques de réponse">
            <thead>
              <tr>
                <th>{group.column}</th>
                <th>Contactés</th>
                <th>Réponses</th>
                <th>Refus</th>
                <th>Taux de réponse</th>
              </tr>
            </thead>
            <tbody>
              {stats.data.map((row) => (
                <tr key={row.key}>
                  <td>{keyLabel(row.key)}</td>
                  <td>{row.contacted}</td>
                  <td>{row.replied}</td>
                  <td>{row.refused}</td>
                  <td>{percent(row.reply_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
