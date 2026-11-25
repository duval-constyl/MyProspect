import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { ApiError, api } from "../api";
import { frenchDate, parisDate } from "../labels";

/** Reminders of one prospect and the history of its follow-up (status, notes, reminders). */
export default function FollowUps({ prospectId }: { prospectId: number }) {
  const queryClient = useQueryClient();
  const key = ["history", prospectId];
  const [dueOn, setDueOn] = useState("");
  const [note, setNote] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  const history = useQuery({ queryKey: key, queryFn: () => api.getHistory(prospectId) });
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: key });
    queryClient.invalidateQueries({ queryKey: ["today"] });
  };
  const plan = useMutation({
    mutationFn: () => api.planFollowup(prospectId, dueOn, note.trim()),
    onSuccess: () => {
      setDueOn("");
      setNote("");
      refresh();
    },
    onError: (exc) => setProblem(exc instanceof ApiError ? exc.message : "Relance impossible pour le moment."),
  });
  const done = useMutation({ mutationFn: (id: number) => api.completeFollowup(id), onSuccess: refresh });

  function submit(event: FormEvent) {
    event.preventDefault();
    setProblem(null);
    if (!dueOn) return setProblem("Choisissez une date de relance.");
    plan.mutate();
  }

  return (
    <section className="card followups-panel" aria-label="Relances et historique">
      <h3>Relances et historique</h3>
      <form className="followup-form" onSubmit={submit}>
        <label className="field">
          Date de relance
          <input type="date" value={dueOn} onChange={(e) => setDueOn(e.target.value)} />
        </label>
        <label className="field">
          Note de relance
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Envoyer le devis" />
        </label>
        <button type="submit" className="secondary" disabled={plan.isPending}>
          Programmer la relance
        </button>
      </form>
      {problem && (
        <p role="alert" className="error">
          {problem}
        </p>
      )}

      {history.data && history.data.followups.length > 0 && (
        <ul className="followups">
          {history.data.followups.map((followup) => (
            <li key={followup.id}>
              <span>
                {frenchDate(followup.due_on)} · {followup.note || "Sans note"}
              </span>
              {followup.done_at ? (
                <span className="hint">faite le {parisDate(followup.done_at)}</span>
              ) : (
                <button type="button" className="secondary" onClick={() => done.mutate(followup.id)}>
                  Fait
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      <h4>Historique</h4>
      {history.data && history.data.events.length === 0 && <p className="hint">Aucun événement pour l'instant.</p>}
      {history.data && history.data.events.length > 0 && (
        <ul className="events">
          {history.data.events.map((event, index) => (
            <li key={`${event.at}-${index}`}>
              <span className="hint">{parisDate(event.at)}</span> <span>{event.text}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
