import { useEffect, useState } from "react";

import { STATUS_LABELS } from "../labels";
import type { Status, Tracking, TrackingPatch } from "../types";

type Props = { tracking: Tracking; onChange: (patch: TrackingPatch) => void; saving?: boolean };

export default function TrackingForm({ tracking, onChange, saving = false }: Props) {
  const [notes, setNotes] = useState(tracking.notes);
  useEffect(() => setNotes(tracking.notes), [tracking.notes]);

  return (
    <section className="card tracking" aria-label="Suivi">
      <h3>Suivi</h3>
      <label className="field">
        Statut
        <select value={tracking.status} onChange={(e) => onChange({ status: e.target.value as Status })}>
          {Object.entries(STATUS_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label className="check">
        <input type="checkbox" checked={tracking.favorite} onChange={(e) => onChange({ favorite: e.target.checked })} />
        Favori
      </label>
      <label className="field">
        Notes
        <textarea rows={5} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      <button type="button" className="primary" disabled={saving || notes === tracking.notes} onClick={() => onChange({ notes })}>
        Enregistrer les notes
      </button>
    </section>
  );
}
