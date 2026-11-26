import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockApi } from "../test/mockApi";
import StatsPage from "./StatsPage";

const BY_OFFER = [
  { key: "web", contacted: 4, replied: 1, refused: 1, reply_rate: 0.25 },
  { key: "none", contacted: 2, replied: 0, refused: 0, reply_rate: 0 },
];
const BY_ZONE = [
  { key: "1", contacted: 3, replied: 2, refused: 0, reply_rate: 2 / 3 },
  { key: "none", contacted: 1, replied: 0, refused: 1, reply_rate: 0 },
];
const ZONES = [
  {
    id: 1, kind: "commune", label: "Villeurbanne (69)", geojson: {}, naf_codes: ["96.02A"],
    collected_at: "2026-11-25T08:00:00Z", watch: false, watch_every_days: 7, last_watch_at: null,
  },
];

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <StatsPage />
    </QueryClientProvider>,
  );
}

function cells(row: HTMLElement) {
  return within(row).getAllByRole("cell").map((cell) => cell.textContent);
}

describe("StatsPage", () => {
  it("test_stats_page_renders_rows_and_percentages", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi({
      "GET /stats/outreach": (request) => ({ body: request.query.get("group_by") === "zone" ? BY_ZONE : BY_OFFER }),
      "GET /zones": { body: ZONES },
    });
    renderPage();

    const table = await screen.findByRole("table", { name: "Statistiques de réponse" });
    await waitFor(() => expect(within(table).getAllByRole("row")).toHaveLength(3));
    const [, web, none] = within(table).getAllByRole("row");
    expect(cells(web)[0]).toBe("Web");
    expect(cells(web).slice(1, 4)).toEqual(["4", "1", "1"]);
    expect(cells(web)[4]).toMatch(/^25\s%$/);
    expect(cells(none)[0]).toBe("Sans brouillon");
    expect(cells(none)[4]).toMatch(/^0\s%$/);
    expect(requests[0].query.get("group_by")).toBe("offer");

    await user.selectOptions(screen.getByLabelText("Regrouper par"), "zone");

    const zoneTable = await screen.findByRole("table", { name: "Statistiques de réponse" });
    await waitFor(() => expect(within(zoneTable).getByText("Villeurbanne (69)")).toBeInTheDocument());
    const [, zone, outside] = within(zoneTable).getAllByRole("row");
    expect(cells(zone)[4]).toMatch(/^67\s%$/);
    expect(cells(outside)[0]).toBe("Hors zone");
    expect(requests.some((r) => r.path === "/stats/outreach" && r.query.get("group_by") === "zone")).toBe(true);
  });

  it("test_stats_page_empty_state", async () => {
    mockApi({ "GET /stats/outreach": { body: [] }, "GET /zones": { body: [] } });
    renderPage();

    expect(await screen.findByText(/Aucun prospect contacté pour l'instant/)).toBeInTheDocument();
  });
});
