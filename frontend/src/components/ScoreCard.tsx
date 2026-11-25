import { OFFER_LABELS } from "../labels";
import { tierColor } from "../tiers";
import type { Score } from "../types";

export default function ScoreCard({ score }: { score: Score }) {
  return (
    <section className="card score-card" aria-label={OFFER_LABELS[score.offer] ?? score.offer}>
      <h3>{OFFER_LABELS[score.offer] ?? score.offer}</h3>
      <div className="score-head">
        <span className="score-ring" style={{ borderColor: tierColor(score.tier) }}>
          {score.value}
        </span>
        <span className="hint">Palier {score.tier} / 6</span>
      </div>
      {score.reasons.length === 0 ? (
        <p className="hint">Aucun défaut relevé.</p>
      ) : (
        <ul className="reasons">
          {score.reasons.map((reason) => (
            <li key={reason.code}>
              <span>{reason.label}</span>
              <span className="points">+{reason.points}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
