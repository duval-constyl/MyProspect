import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError, api } from "../api";
import ContactList from "../components/ContactList";
import OutreachDrafts from "../components/OutreachDrafts";
import ScoreCard from "../components/ScoreCard";
import TrackingForm from "../components/TrackingForm";
import { MISSING, OFFERS, frenchDate, tradeLabel } from "../labels";
import type { ProspectDetail, SiteAnalysis, TrackingPatch } from "../types";

function yesNo(value: boolean): string {
  return value ? "oui" : "non";
}

export default function ProspectPage({ id }: { id: number }) {
  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState<string | null>(null);
  const key = ["prospect", id];

  const prospect = useQuery({ queryKey: key, queryFn: () => api.getProspect(id) });

  function afterChange() {
    queryClient.invalidateQueries({ queryKey: ["prospects"] });
  }

  function failed(exc: unknown) {
    setActionError(exc instanceof ApiError ? exc.message : "Action impossible pour le moment.");
  }

  const tracking = useMutation({
    mutationFn: (patch: TrackingPatch) => api.patchTracking(id, patch),
    onSuccess: (updated) => {
      queryClient.setQueryData<ProspectDetail>(key, (current) => (current ? { ...current, tracking: updated } : current));
      afterChange();
    },
    onError: failed,
  });

  const doNotContact = useMutation({
    mutationFn: () => api.doNotContact(id),
    onSuccess: (updated) => {
      queryClient.setQueryData<ProspectDetail>(key, (current) => (current ? { ...current, tracking: updated } : current));
      afterChange();
    },
    onError: failed,
  });

  const remove = useMutation({
    mutationFn: () => api.deleteProspect(id),
    onSuccess: () => {
      afterChange();
      window.location.hash = "#/prospects";
    },
    onError: failed,
  });

  if (prospect.isError) {
    return (
      <div className="detail-page">
        <p role="alert" className="error">
          {prospect.error.message}
        </p>
        <a href="#/prospects">Retour à la liste</a>
      </div>
    );
  }
  if (!prospect.data) return <p className="hint detail-page">Chargement de la fiche…</p>;

  const data = prospect.data;

  function confirmDelete() {
    const message =
      `Supprimer définitivement « ${data.name} » ?\n` +
      "Ses coordonnées, son analyse, ses scores et son suivi seront effacés, " +
      "et l'entreprise ne sera plus jamais récoltée.";
    if (window.confirm(message)) remove.mutate();
  }

  return (
    <div className="detail-page">
      <a href="#/prospects">← Retour à la liste</a>

      <header className="detail-head">
        <h1>{data.name}</h1>
        <p className="hint">
          SIRET {data.siret} · {tradeLabel(data.naf)} ({data.naf}) · {data.address || MISSING}
        </p>
        <p className="hint">
          Création : {frenchDate(data.created_on)} · Tranche d'effectif : {data.effectif_code ?? MISSING}
          {data.is_individual ? " · Entreprise individuelle" : ""}
        </p>
        {data.opposed_to_prospecting && (
          <p className="banner warning">
            Opposée à la prospection commerciale (déclaration au registre officiel). À vous de décider avant
            tout contact.
          </p>
        )}
      </header>

      {actionError && (
        <p role="alert" className="error">
          {actionError}
        </p>
      )}

      <div className="detail-grid">
        <div className="detail-main">
          <section className="card" aria-label="Coordonnées">
            <h3>Coordonnées</h3>
            <ContactList contacts={data.contacts} />
          </section>

          <section className="card" aria-label="Priorité de contact">
            <h3>Priorité de contact</h3>
            {OFFERS.map(({ value, label }) => {
              const priority = data.priority_by_offer?.[value] ?? (value === "web" ? data.priority : undefined);
              if (!priority) return null;
              return (
                <div key={value} className="priority-block">
                  <h4>
                    Priorité {label} : {priority.value}
                  </h4>
                  {priority.reasons.length === 0 ? (
                    <p className="hint">Aucun critère de priorité rempli.</p>
                  ) : (
                    <ul className="reasons">
                      {priority.reasons.map((reason) => (
                        <li key={reason.code}>
                          <span>{reason.label}</span>
                          <span className="points">+{reason.points}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </section>

          {data.scores.map((score) => (
            <ScoreCard key={score.offer} score={score} />
          ))}

          <section className="card" aria-label="Analyse du site">
            <h3>Analyse du site</h3>
            {data.site_analysis ? (
              <SiteAnalysisSummary analysis={data.site_analysis} />
            ) : (
              <p className="hint">Aucune analyse de site : pas de site connu.</p>
            )}
          </section>
        </div>

        <div className="detail-side">
          <TrackingForm tracking={data.tracking} onChange={(patch) => tracking.mutate(patch)} saving={tracking.isPending} />
          <OutreachDrafts prospectId={data.id} opposed={data.opposed_to_prospecting} />
          <section className="card actions" aria-label="Actions">
            <button type="button" className="secondary" onClick={() => doNotContact.mutate()} disabled={doNotContact.isPending}>
              Ne plus contacter
            </button>
            <p className="hint">Passe le statut à « Refusé » et l'entreprise ne sera plus récoltée. La fiche est gardée.</p>
            <button type="button" className="danger" onClick={confirmDelete} disabled={remove.isPending}>
              Supprimer définitivement
            </button>
          </section>
        </div>
      </div>
    </div>
  );
}

function SiteAnalysisSummary({ analysis }: { analysis: SiteAnalysis }) {
  if (!analysis.reachable) {
    return (
      <p>
        Site inaccessible lors de l'analyse du {frenchDate(analysis.analyzed_at)} ({analysis.url}).
      </p>
    );
  }
  return (
    <ul className="facts">
      <li>
        Adresse analysée :{" "}
        <a href={analysis.url} target="_blank" rel="noopener noreferrer">
          {analysis.url}
        </a>
      </li>
      <li>HTTPS : {yesNo(analysis.https)}</li>
      <li>Titre : {yesNo(analysis.has_title)}</li>
      <li>Description : {yesNo(analysis.has_description)}</li>
      <li>Titre principal (H1) : {yesNo(analysis.has_h1)}</li>
      <li>Adapté au mobile (viewport) : {yesNo(analysis.has_viewport)}</li>
      <li>Vitesse mobile (PageSpeed) : {analysis.mobile_perf === null ? "non mesurée" : `${analysis.mobile_perf}/100`}</li>
      <li>Temps de réponse : {analysis.response_ms === null ? MISSING : `${analysis.response_ms} ms`}</li>
      <li>Technologies : {analysis.tech.length ? analysis.tech.join(", ") : "aucune détectée"}</li>
      <li>Analysé le {frenchDate(analysis.analyzed_at)}</li>
    </ul>
  );
}
