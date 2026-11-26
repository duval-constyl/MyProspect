import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { ALERT_KIND_LABELS, WATCH_FREQUENCIES, parisDate, tradeLabel } from "../labels";
import type { ZoneInfo, ZonePatch } from "../types";

/** « Alertes » : what changed in the watched zones, the zones to watch, possible duplicates. */
export default function AlertsPage() {
  return (
    <div className="alerts-page">
      <AlertsSection />
      <ZonesSection />
      <DuplicatesSection />
    </div>
  );
}

function AlertsSection() {
  const queryClient = useQueryClient();
  const alerts = useQuery({ queryKey: ["alerts", "unseen"], queryFn: () => api.listAlerts(true) });
  const seen = useMutation({
    mutationFn: (id: number) => api.markAlertSeen(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });

  return (
    <section className="card" aria-label="Alertes">
      <h2>Alertes</h2>
      {alerts.isError ? (
        <p role="alert" className="error">
          {alerts.error.message}
        </p>
      ) : !alerts.data ? (
        <p className="hint">Chargement…</p>
      ) : alerts.data.length === 0 ? (
        <p className="hint">Aucune nouvelle alerte.</p>
      ) : (
        <ul className="followups">
          {alerts.data.map((alert) => (
            <li key={alert.id}>
              <span className="followup-date">{parisDate(alert.created_at)}</span>
              <strong>{ALERT_KIND_LABELS[alert.kind] ?? alert.kind}</strong>
              <a href={`#/prospects/${alert.prospect_id}`}>{alert.prospect_name}</a>
              <span className="followup-note">{alert.zone_label}</span>
              <button type="button" className="secondary" disabled={seen.isPending} onClick={() => seen.mutate(alert.id)}>
                Vu
              </button>
            </li>
          ))}
        </ul>
      )}
      {seen.isError && (
        <p role="alert" className="error">
          {seen.error.message}
        </p>
      )}
    </section>
  );
}

function ZonesSection() {
  const queryClient = useQueryClient();
  const zones = useQuery({ queryKey: ["zones"], queryFn: api.listZones });
  const update = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: ZonePatch }) => api.patchZone(id, patch),
    onSuccess: (zone) =>
      queryClient.setQueryData<ZoneInfo[]>(["zones"], (list) => list?.map((item) => (item.id === zone.id ? zone : item))),
  });

  return (
    <section className="card" aria-label="Zones suivies">
      <h2>Zones suivies</h2>
      <p className="hint">
        Une zone suivie est récoltée de nouveau à la fréquence choisie ; la première veille fixe le point de départ, sans
        alerte.
      </p>
      {zones.isError ? (
        <p role="alert" className="error">
          {zones.error.message}
        </p>
      ) : !zones.data ? (
        <p className="hint">Chargement…</p>
      ) : zones.data.length === 0 ? (
        <p className="hint">Aucune zone récoltée : lancez une récolte depuis la carte.</p>
      ) : (
        <ul className="followups">
          {zones.data.map((zone) => (
            <li key={zone.id}>
              <strong>{zone.label}</strong>
              <span className="followup-note">{zone.naf_codes.map(tradeLabel).join(", ")}</span>
              <label>
                <input
                  type="checkbox"
                  checked={zone.watch}
                  disabled={update.isPending}
                  onChange={(event) => update.mutate({ id: zone.id, patch: { watch: event.target.checked } })}
                />{" "}
                Suivre cette zone
              </label>
              <label>
                Fréquence{" "}
                <select
                  value={zone.watch_every_days}
                  disabled={update.isPending}
                  onChange={(event) =>
                    update.mutate({ id: zone.id, patch: { watch_every_days: Number(event.target.value) } })
                  }
                >
                  {frequencies(zone.watch_every_days).map((option) => (
                    <option key={option.days} value={option.days}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <span className="hint">
                {zone.last_watch_at ? `Dernière veille : ${parisDate(zone.last_watch_at)}` : "Pas encore de veille"}
              </span>
            </li>
          ))}
        </ul>
      )}
      {update.isError && (
        <p role="alert" className="error">
          {update.error.message}
        </p>
      )}
    </section>
  );
}

/** The usual choices, plus the zone's current value when it is another one. */
function frequencies(current: number) {
  if (WATCH_FREQUENCIES.some((option) => option.days === current)) return WATCH_FREQUENCIES;
  return [...WATCH_FREQUENCIES, { days: current, label: `Tous les ${current} jours` }].sort((a, b) => a.days - b.days);
}

function DuplicatesSection() {
  const duplicates = useQuery({ queryKey: ["duplicates"], queryFn: api.listDuplicates });

  return (
    <section className="card" aria-label="Doublons possibles">
      <h2>Doublons possibles</h2>
      {duplicates.isError ? (
        <p role="alert" className="error">
          {duplicates.error.message}
        </p>
      ) : !duplicates.data ? (
        <p className="hint">Chargement…</p>
      ) : duplicates.data.length === 0 ? (
        <p className="hint">Aucun doublon repéré.</p>
      ) : (
        <ul className="followups">
          {duplicates.data.map((pair) => (
            <li key={`${pair.first.id}-${pair.second.id}`}>
              <a href={`#/prospects/${pair.first.id}`}>{pair.first.name}</a>
              <span>et</span>
              <a href={`#/prospects/${pair.second.id}`}>{pair.second.name}</a>
              <span className="hint">même nom, à moins de 30 m</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
