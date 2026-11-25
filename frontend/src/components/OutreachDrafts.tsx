import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError, api } from "../api";
import { OFFERS, frenchDate, offerLabel } from "../labels";
import type { Channel, Draft, Offer } from "../types";

const CHANNEL_LABELS: Record<Channel, string> = { email: "E-mail", call: "Script d'appel" };
const SOURCE_LABELS: Record<Draft["source"], string> = {
  llm: "Rédigé par l'IA, à relire",
  template: "Modèle fixe, à relire",
};

type Props = { prospectId: number; opposed: boolean };

/** Prepares drafts for Duval to read and send himself: the tool never sends anything. */
export default function OutreachDrafts({ prospectId, opposed }: Props) {
  const queryClient = useQueryClient();
  const [offer, setOffer] = useState<Offer>("web");
  const [problem, setProblem] = useState<string | null>(null);
  const key = ["drafts", prospectId];

  const drafts = useQuery({ queryKey: key, queryFn: () => api.listDrafts(prospectId) });
  const prepare = useMutation({
    mutationFn: (channel: Channel) => api.prepareDraft(prospectId, offer, channel),
    onMutate: () => setProblem(null),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
    onError: (exc) => setProblem(exc instanceof ApiError ? exc.message : "Brouillon impossible pour le moment."),
  });

  return (
    <section className="card drafts" aria-label="Brouillons d'approche">
      <h3>Brouillons d'approche</h3>
      <p className="hint">L'outil n'envoie rien : relisez, modifiez, puis envoyez vous-même.</p>
      {opposed && (
        <p className="hint warning-text">Entreprise opposée à la prospection commerciale : à vous de décider.</p>
      )}
      <div className="draft-actions">
        <label className="field">
          Offre du brouillon
          <select value={offer} onChange={(e) => setOffer(e.target.value as Offer)}>
            {OFFERS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="secondary" disabled={prepare.isPending} onClick={() => prepare.mutate("email")}>
          Préparer un e-mail
        </button>
        <button type="button" className="secondary" disabled={prepare.isPending} onClick={() => prepare.mutate("call")}>
          Préparer un script d'appel
        </button>
      </div>
      {prepare.isPending && <p className="hint">Préparation du brouillon…</p>}
      {problem && (
        <p role="alert" className="error">
          {problem}
        </p>
      )}
      {drafts.data && drafts.data.length === 0 && <p className="hint">Aucun brouillon pour l'instant.</p>}
      {drafts.data?.map((draft) => <DraftCard key={draft.id} draft={draft} />)}
    </section>
  );
}

function DraftCard({ draft }: { draft: Draft }) {
  const [copied, setCopied] = useState(false);
  const fullText = draft.subject ? `Objet : ${draft.subject}\n\n${draft.body}` : draft.body;

  async function copy() {
    try {
      await navigator.clipboard.writeText(fullText);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <article className="draft">
      <header className="hint">
        {CHANNEL_LABELS[draft.channel]} · {offerLabel(draft.offer)} · {frenchDate(draft.created_at)} ·{" "}
        <span className="badge">{SOURCE_LABELS[draft.source]}</span>
      </header>
      {draft.subject && <p className="draft-subject">Objet : {draft.subject}</p>}
      <p className="draft-body">{draft.body}</p>
      <button type="button" className="secondary" onClick={copy}>
        {copied ? "Copié" : "Copier"}
      </button>
    </article>
  );
}
