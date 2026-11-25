import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockApi } from "../test/mockApi";
import type { ProspectListItem } from "../types";
import ProspectsPage from "./ProspectsPage";

function item(overrides: Partial<ProspectListItem>): ProspectListItem {
  return {
    id: 1,
    siret: "11111111100011",
    name: "SALON ECLAT",
    naf: "96.02A",
    address: "12 RUE DE LA REPUBLIQUE 69001 LYON",
    city: "LYON",
    lat: 45.76,
    long: 4.83,
    score_web: 75,
    tier: 5,
    priority: 56,
    status: "new",
    favorite: false,
    has_site: false,
    phone: "04 78 00 00 01",
    email: null,
    website: null,
    opposed_to_prospecting: false,
    ...overrides,
  };
}

const LIST = {
  items: [
    item({}),
    item({
      id: 2,
      siret: "22222222200022",
      name: "GARAGE MARTIN",
      naf: "45.20A",
      city: "VILLEURBANNE",
      score_web: 20,
      tier: 2,
      priority: 36,
      status: "contacted",
      phone: null,
      has_site: true,
      website: "https://garage-martin.fr",
      opposed_to_prospecting: true,
    }),
  ],
  total: 2,
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProspectsPage />
    </QueryClientProvider>,
  );
}

function lastListQuery(requests: { path: string; query: URLSearchParams }[]) {
  return [...requests].reverse().find((r) => r.path === "/prospects")!.query;
}

describe("ProspectsPage", () => {
  it("test_shows_rows_with_trade_city_score_priority_status", async () => {
    mockApi({ "GET /prospects": { body: LIST } });

    renderPage();

    const row = (await screen.findByText("GARAGE MARTIN")).closest("tr")!;
    expect(within(row).getByText("Garage")).toBeInTheDocument();
    expect(within(row).getByText("VILLEURBANNE")).toBeInTheDocument();
    expect(within(row).getByText("20")).toBeInTheDocument();
    expect(within(row).getByText("36")).toBeInTheDocument();
    expect(within(row).getByText("Contacté")).toBeInTheDocument();
    expect(within(row).getByText("Opposée à la prospection")).toBeInTheDocument();
    expect(screen.getByText("2 prospects")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "SALON ECLAT" })).toHaveAttribute("href", "#/prospects/1");
  });

  it("test_changing_filter_refetches_with_params", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi({ "GET /prospects": { body: LIST } });
    renderPage();
    await screen.findByText("SALON ECLAT");

    await user.selectOptions(screen.getByLabelText("Site connu"), "Sans site");
    await user.selectOptions(screen.getByLabelText("Métier"), "Coiffure");
    await user.type(screen.getByLabelText("Score minimum"), "40");
    await user.selectOptions(screen.getByLabelText("Statut"), "À contacter");
    await user.click(screen.getByLabelText("Favoris seulement"));
    await user.type(screen.getByLabelText("Rechercher (nom ou SIRET)"), "eclat");

    await waitFor(() => {
      const query = lastListQuery(requests);
      expect(query.get("has_site")).toBe("false");
      expect(query.get("naf")).toBe("96.02A");
      expect(query.get("score_min")).toBe("40");
      expect(query.get("status")).toBe("to_contact");
      expect(query.get("favorite")).toBe("true");
      expect(query.get("q")).toBe("eclat");
      expect(query.get("page")).toBe("1");
    });
  });

  it("test_sort_by_priority_toggles_direction", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi({ "GET /prospects": { body: LIST } });
    renderPage();
    await screen.findByText("SALON ECLAT");
    expect(lastListQuery(requests).get("sort")).toBe("priority");
    expect(lastListQuery(requests).get("order")).toBe("desc");

    await user.click(screen.getByRole("button", { name: /Priorité/ }));
    await waitFor(() => expect(lastListQuery(requests).get("order")).toBe("asc"));
    expect(lastListQuery(requests).get("sort")).toBe("priority");

    await user.click(screen.getByRole("button", { name: /Priorité/ }));
    await waitFor(() => expect(lastListQuery(requests).get("order")).toBe("desc"));

    await user.click(screen.getByRole("button", { name: /Nom/ }));
    await waitFor(() => {
      expect(lastListQuery(requests).get("sort")).toBe("name");
      expect(lastListQuery(requests).get("order")).toBe("asc");
    });
  });

  it("test_export_link_contains_active_filters", async () => {
    const user = userEvent.setup();
    mockApi({ "GET /prospects": { body: LIST } });
    renderPage();
    await screen.findByText("SALON ECLAT");

    await user.selectOptions(screen.getByLabelText("Site connu"), "Avec site");
    await user.selectOptions(screen.getByLabelText("Opposition à la prospection"), "Non opposées");

    const link = screen.getByRole("link", { name: "Exporter en CSV" });
    await waitFor(() => {
      const href = link.getAttribute("href")!;
      expect(href.startsWith("/api/exports/prospects.csv?")).toBe(true);
      const query = new URLSearchParams(href.split("?")[1]);
      expect(query.get("has_site")).toBe("true");
      expect(query.get("opposed")).toBe("false");
      expect(query.get("sort")).toBe("priority");
      expect(query.has("page")).toBe(false);
    });
  });

  it("test_row_without_phone_shows_dash_not_empty_or_null", async () => {
    mockApi({ "GET /prospects": { body: LIST } });

    renderPage();

    const row = (await screen.findByText("GARAGE MARTIN")).closest("tr")!;
    const phoneCell = row.querySelector("td[data-column='phone']")!;
    expect(phoneCell.textContent).toBe("—");
    expect(row.textContent).not.toMatch(/null|undefined/);
  });

  it("test_empty_list_shows_message", async () => {
    mockApi({ "GET /prospects": { body: { items: [], total: 0 } } });

    renderPage();

    expect(await screen.findByText(/Aucun prospect/)).toBeInTheDocument();
  });
});
