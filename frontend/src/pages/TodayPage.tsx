import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { MISSING, STATUS_LABELS, frenchDate, offerLabel } from "../labels";

/** « Aujourd'hui » : reminders due (Paris calendar day) and the prospects to contact first. */
export default function TodayPage() {
  const queryClient = useQueryClient();
  const today = useQuery({ queryKey: ["today"], queryFn: api.getToday });
  const done = useMutation({
    mutationFn: (followupId: number) => api.completeFollowup(followupId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["today"] }),
  });

  if (today.isError) {
    return (
      <p role="alert" className="error today-page">
        {today.error.message}
      </p>
    );
  }
  if (!today.data) return <p className="hint today-page">Chargement…</p>;

  return (
    <div className="today-page">
      <section className="card" aria-label="Relances du jour">
        <h2>Relances du jour</h2>
        {today.data.followups_due.length === 0 ? (
          <p className="hint">Aucune relance pour aujourd'hui.</p>
        ) : (
          <ul className="followups">
            {today.data.followups_due.map((followup) => (
              <li key={followup.id}>
                <span className="followup-date">{frenchDate(followup.due_on)}</span>
                <a href={`#/prospects/${followup.prospect_id}`}>{followup.prospect_name}</a>
                <span>{followup.phone ?? MISSING}</span>
                <span className="followup-note">{followup.note || "Sans note"}</span>
                <button type="button" className="secondary" disabled={done.isPending} onClick={() => done.mutate(followup.id)}>
                  Fait
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card" aria-label="À contacter en priorité">
        <h2>À contacter en priorité</h2>
        {today.data.top_priority.length === 0 ? (
          <p className="hint">Aucun prospect à contacter : lancez une récolte depuis la carte.</p>
        ) : (
          <table className="prospects">
            <thead>
              <tr>
                <th>Nom</th>
                <th>Ville</th>
                <th>Téléphone</th>
                <th>Meilleure offre</th>
                <th>Priorité</th>
                <th>Statut</th>
              </tr>
            </thead>
            <tbody>
              {today.data.top_priority.map((prospect) => (
                <tr key={prospect.id}>
                  <td>
                    <a href={`#/prospects/${prospect.id}`}>{prospect.name}</a>
                  </td>
                  <td>{prospect.city ?? MISSING}</td>
                  <td data-column="phone">{prospect.phone ?? MISSING}</td>
                  <td>{offerLabel(prospect.best_offer)}</td>
                  <td>{prospect.priority}</td>
                  <td>{STATUS_LABELS[prospect.status] ?? prospect.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
