import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "../api";
import MapView, { type ViewState } from "../components/MapView";
import ZoneControls from "../components/ZoneControls";
import { OFFERS, offerLabel } from "../labels";
import { TIER_COLORS } from "../tiers";
import type { CollectBody, LatLong, Offer, ZoneKind } from "../types";

type Props = {
  /** Interval between two job checks while a collection runs. */
  pollMs?: number;
};

const FINISHED = ["done", "failed"];

export default function MapPage({ pollMs = 1000 }: Props) {
  const queryClient = useQueryClient();
  const [view, setView] = useState<ViewState | null>(null);
  const [offer, setOffer] = useState<Offer>("web");
  const [zoneKind, setZoneKind] = useState<ZoneKind>("commune");
  const [drawing, setDrawing] = useState<[number, number][]>([]);
  const [jobId, setJobId] = useState<number | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const bbox = view?.bbox;
  const zoom = view ? Math.floor(view.zoom) : 0;

  const stats = useQuery({
    queryKey: ["stats", bbox?.join(",")],
    queryFn: () => api.getStats(bbox!),
    enabled: !!bbox,
  });
  const clusters = useQuery({
    queryKey: ["clusters", bbox?.join(","), zoom, offer],
    queryFn: () => api.getClusters(bbox!, zoom, offer),
    enabled: !!bbox,
  });
  const job = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.getJob(jobId!),
    enabled: jobId !== null,
    refetchInterval: (query) => (FINISHED.includes(query.state.data?.state ?? "") ? false : pollMs),
  });

  const jobState = job.data?.state;
  useEffect(() => {
    if (jobState && FINISHED.includes(jobState)) {
      queryClient.invalidateQueries({ queryKey: ["stats"] });
      queryClient.invalidateQueries({ queryKey: ["clusters"] });
      queryClient.invalidateQueries({ queryKey: ["prospects"] });
    }
  }, [jobState, queryClient]);

  const onViewChange = useCallback((next: ViewState) => setView(next), []);

  const onMapClick = useCallback(
    (point: LatLong) => {
      if (zoneKind === "polygon") setDrawing((points) => [...points, [point.long, point.lat]]);
    },
    [zoneKind],
  );

  const onProspectClick = useCallback((prospectId: number) => {
    window.location.hash = `#/prospects/${prospectId}`;
  }, []);

  async function collect(body: CollectBody) {
    setError(null);
    setSending(true);
    try {
      const { job_id } = await api.collectZone(body);
      setJobId(job_id);
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : "Erreur inattendue pendant l'envoi de la récolte.");
    } finally {
      setSending(false);
    }
  }

  const running = jobId !== null && !!job.data && !FINISHED.includes(job.data.state);

  return (
    <div className="map-page">
      <aside className="side-panel">
        <ZoneControls
          onCollect={collect}
          mapCenter={view?.center ?? null}
          drawnPoints={drawing}
          onKindChange={(kind) => {
            setZoneKind(kind);
            if (kind !== "polygon") setDrawing([]);
          }}
          onClearDrawing={() => setDrawing([])}
          busy={sending || running}
        />

        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {job.data && <JobProgress state={job.data.state} done={job.data.done} total={job.data.total} error={job.data.error} />}

        <section className="counters" aria-label="Compteurs de la vue">
          {stats.data ? (
            <>
              <p>Dans la vue : {stats.data.in_view}</p>
              <p>Avec site : {stats.data.with_site}</p>
              <p>Sans site : {stats.data.without_site}</p>
            </>
          ) : (
            <p className="hint">Compteurs en cours de chargement…</p>
          )}
        </section>

        <section className="legend" aria-label="Légende des couleurs">
          <label className="field">
            Offre affichée
            <select value={offer} onChange={(e) => setOffer(e.target.value as Offer)}>
              {OFFERS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <p>Opportunité {offerLabel(offer)}, du palier 1 au palier 6 :</p>
          <div className="legend-scale">
            {TIER_COLORS.map((color, index) => (
              <span key={color} style={{ background: color }} title={`Palier ${index + 1}`} />
            ))}
          </div>
        </section>
      </aside>

      <MapView
        clusters={clusters.data?.clusters ?? []}
        drawing={drawing}
        onViewChange={onViewChange}
        onMapClick={onMapClick}
        onProspectClick={onProspectClick}
      />
    </div>
  );
}

function JobProgress({ state, done, total, error }: { state: string; done: number; total: number; error: string | null }) {
  if (state === "failed") {
    return (
      <p role="alert" className="error">
        {error ?? "Récolte interrompue."}
      </p>
    );
  }
  if (state === "done") {
    return <p className="success">Récolte terminée : {total} entreprises.</p>;
  }
  return (
    <div className="progress">
      <p>{state === "pending" ? "Récolte en attente…" : `Récolte en cours : ${done} / ${total}`}</p>
      <progress value={done} max={Math.max(total, 1)} />
    </div>
  );
}
