import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api";
import { MISSING, OFFERS, STATUS_LABELS, TRADES, offerLabel, tradeLabel } from "../labels";
import { tierColor } from "../tiers";
import type { Offer, ProspectFilters, SortKey, Status } from "../types";

const PER_PAGE = 50;
const DEFAULT_ORDER: Record<SortKey, "asc" | "desc"> = { priority: "desc", score: "desc", name: "asc" };

function boolFromSelect(value: string): boolean | undefined {
  return value === "" ? undefined : value === "true";
}

type SortButtonProps = { column: SortKey; label: string; filters: ProspectFilters; onSort: (key: SortKey) => void };

function SortButton({ column, label, filters, onSort }: SortButtonProps) {
  const arrow = filters.sort === column ? (filters.order === "asc" ? " ↑" : " ↓") : "";
  return (
    <button type="button" className="sort" onClick={() => onSort(column)}>
      {label}
      {arrow}
    </button>
  );
}

export default function ProspectsPage() {
  const [filters, setFilters] = useState<ProspectFilters>({ offer: "web", sort: "priority", order: "desc" });
  const [page, setPage] = useState(1);

  const list = useQuery({
    queryKey: ["prospects", filters, page],
    queryFn: () => api.listProspects(filters, page, PER_PAGE),
    placeholderData: keepPreviousData,
  });

  function update(changes: Partial<ProspectFilters>) {
    setFilters((current) => ({ ...current, ...changes }));
    setPage(1);
  }

  function sortBy(key: SortKey) {
    setFilters((current) =>
      current.sort === key
        ? { ...current, order: current.order === "asc" ? "desc" : "asc" }
        : { ...current, sort: key, order: DEFAULT_ORDER[key] },
    );
    setPage(1);
  }

  const total = list.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PER_PAGE));

  return (
    <div className="list-page">
      <section className="filters" aria-label="Filtres">
        <label className="field">
          Offre
          <select value={filters.offer} onChange={(e) => update({ offer: e.target.value as Offer })}>
            {OFFERS.map((offer) => (
              <option key={offer.value} value={offer.value}>
                {offer.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Métier
          <select value={filters.naf ?? ""} onChange={(e) => update({ naf: e.target.value || undefined })}>
            <option value="">Tous</option>
            {TRADES.map((trade) => (
              <option key={trade.naf} value={trade.naf}>
                {trade.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Site connu
          <select
            value={filters.has_site === undefined ? "" : String(filters.has_site)}
            onChange={(e) => update({ has_site: boolFromSelect(e.target.value) })}
          >
            <option value="">Tous</option>
            <option value="true">Avec site</option>
            <option value="false">Sans site</option>
          </select>
        </label>
        <label className="field">
          Score minimum
          <input
            type="number"
            min="0"
            max="100"
            value={filters.score_min ?? ""}
            onChange={(e) => update({ score_min: e.target.value === "" ? undefined : Number(e.target.value) })}
          />
        </label>
        <label className="field">
          Statut
          <select
            value={filters.status ?? ""}
            onChange={(e) => update({ status: (e.target.value || undefined) as Status | undefined })}
          >
            <option value="">Tous</option>
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Opposition à la prospection
          <select
            value={filters.opposed === undefined ? "" : String(filters.opposed)}
            onChange={(e) => update({ opposed: boolFromSelect(e.target.value) })}
          >
            <option value="">Toutes</option>
            <option value="true">Opposées</option>
            <option value="false">Non opposées</option>
          </select>
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={filters.favorite === true}
            onChange={(e) => update({ favorite: e.target.checked ? true : undefined })}
          />
          Favoris seulement
        </label>
        <label className="field search">
          Rechercher (nom ou SIRET)
          <input type="search" value={filters.q ?? ""} onChange={(e) => update({ q: e.target.value || undefined })} />
        </label>
        <a className="secondary export" href={api.exportUrl(filters)} download>
          Exporter en CSV
        </a>
      </section>

      {list.isError && (
        <p role="alert" className="error">
          {list.error.message}
        </p>
      )}

      <p className="hint">{total} prospects</p>

      <table className="prospects">
        <thead>
          <tr>
            <th>
              <SortButton column="name" label="Nom" filters={filters} onSort={sortBy} />
            </th>
            <th>Métier</th>
            <th>Ville</th>
            <th>Téléphone</th>
            <th>
              <SortButton column="score" label={`Score ${offerLabel(filters.offer)}`} filters={filters} onSort={sortBy} />
            </th>
            <th>
              <SortButton column="priority" label="Priorité" filters={filters} onSort={sortBy} />
            </th>
            <th>Statut</th>
          </tr>
        </thead>
        <tbody>
          {list.data?.items.map((prospect) => (
            <tr key={prospect.id}>
              <td>
                {prospect.favorite && (
                  <span className="favorite" title="Favori" aria-label="Favori">
                    ★{" "}
                  </span>
                )}
                <a href={`#/prospects/${prospect.id}`}>{prospect.name}</a>
                {prospect.opposed_to_prospecting && <span className="badge warning">Opposée à la prospection</span>}
              </td>
              <td>{tradeLabel(prospect.naf)}</td>
              <td>{prospect.city ?? MISSING}</td>
              <td data-column="phone">{prospect.phone ?? MISSING}</td>
              <td>
                {prospect.score === null ? (
                  MISSING
                ) : (
                  <span className="score-chip" style={{ borderColor: tierColor(prospect.tier) }}>
                    {prospect.score}
                  </span>
                )}
              </td>
              <td>{prospect.priority}</td>
              <td>{STATUS_LABELS[prospect.status] ?? prospect.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {list.data && list.data.items.length === 0 && (
        <p className="hint">Aucun prospect ne correspond à ces filtres. Lancez une récolte depuis la carte.</p>
      )}

      {pages > 1 && (
        <nav className="pager" aria-label="Pages">
          <button type="button" className="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Précédent
          </button>
          <span>
            Page {page} / {pages}
          </span>
          <button type="button" className="secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>
            Suivant
          </button>
        </nav>
      )}
    </div>
  );
}
