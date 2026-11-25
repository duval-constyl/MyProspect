import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockApi } from "../test/mockApi";
import AlertsPage from "./AlertsPage";

const ALERTS = [
  {
    id: 4, kind: "new_company", zone_id: 1, zone_label: "Villeurbanne (69)", prospect_id: 12,
    prospect_name: "NOUVEAU GARAGE", created_at: "2026-11-25T08:00:00Z", seen_at: null,
  },
  {
    id: 5, kind: "closed", zone_id: 1, zone_label: "Villeurbanne (69)", prospect_id: 13,
    prospect_name: "ANCIEN SALON", created_at: "2026-11-24T08:00:00Z", seen_at: null,
  },
];
const ZONES = [
  {
    id: 1, kind: "commune", label: "Villeurbanne (69)", geojson: {}, naf_codes: ["45.20A", "96.02A"],
    collected_at: "2026-11-25T08:00:00Z", watch: true, watch_every_days: 7, last_watch_at: "2026-11-25T08:00:00Z",
  },
  {
    id: 2, kind: "circle", label: "Cercle de 2 km", geojson: {}, naf_codes: ["56.10A"],
    collected_at: "2026-11-20T08:00:00Z", watch: false, watch_every_days: 7, last_watch_at: null,
  },
];
const DUPLICATES = [{ first: { id: 20, name: "SALON ECLAT" }, second: { id: 21, name: "SALON ECLAT SARL" } }];

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AlertsPage />
    </QueryClientProvider>,
  );
}

describe("AlertsPage", () => {
  it("test_alerts_page_lists_unseen_alerts_and_marks_seen", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi({
      "GET /alerts": [{ body: ALERTS }, { body: ALERTS.slice(1) }],
      "GET /zones": { body: ZONES },
      "GET /prospects/duplicates": { body: [] },
      "POST /alerts/4/seen": { body: { ...ALERTS[0], seen_at: "2026-11-25T10:00:00Z" } },
    });
    renderPage();

    const panel = await screen.findByRole("region", { name: "Alertes" });
    const first = (await within(panel).findByText("NOUVEAU GARAGE")).closest("li")!;
    expect(within(first).getByText("Nouvelle entreprise")).toBeInTheDocument();
    expect(within(first).getByText(/Villeurbanne \(69\)/)).toBeInTheDocument();
    expect(within(panel).getByRole("link", { name: "NOUVEAU GARAGE" })).toHaveAttribute("href", "#/prospects/12");
    expect(within(panel).getByText("Entreprise fermée")).toBeInTheDocument();
    expect(requests.find((r) => r.path === "/alerts")!.query.get("unseen")).toBe("true");

    await user.click(within(first).getByRole("button", { name: "Vu" }));

    await waitFor(() => expect(requests.some((r) => r.method === "POST" && r.path === "/alerts/4/seen")).toBe(true));
    await waitFor(() => expect(within(panel).queryByText("NOUVEAU GARAGE")).not.toBeInTheDocument());
  });

  it("test_toggle_zone_watch_sends_patch", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi({
      "GET /alerts": { body: [] },
      "GET /zones": { body: ZONES },
      "GET /prospects/duplicates": { body: [] },
      "PATCH /zones/2": { body: { ...ZONES[1], watch: true } },
      "PATCH /zones/1": { body: { ...ZONES[0], watch_every_days: 14 } },
    });
    renderPage();

    const zones = await screen.findByRole("region", { name: "Zones suivies" });
    const circle = (await within(zones).findByText("Cercle de 2 km")).closest("li")!;
    await user.click(within(circle).getByLabelText("Suivre cette zone"));
    const commune = within(zones).getByText("Villeurbanne (69)").closest("li")!;
    await user.selectOptions(within(commune).getByLabelText("Fréquence"), "14");

    await waitFor(() => expect(requests.filter((r) => r.method === "PATCH")).toHaveLength(2));
    const patches = requests.filter((r) => r.method === "PATCH").map((r) => [r.path, r.body]);
    expect(patches).toEqual([
      ["/zones/2", { watch: true }],
      ["/zones/1", { watch_every_days: 14 }],
    ]);
    expect(await screen.findByText("Aucune nouvelle alerte.")).toBeInTheDocument();
  });

  it("test_duplicates_section_lists_pairs", async () => {
    mockApi({
      "GET /alerts": { body: [] },
      "GET /zones": { body: [] },
      "GET /prospects/duplicates": { body: DUPLICATES },
    });
    renderPage();

    const section = await screen.findByRole("region", { name: "Doublons possibles" });
    await waitFor(() => expect(within(section).getByRole("link", { name: "SALON ECLAT" })).toHaveAttribute("href", "#/prospects/20"));
    expect(within(section).getByRole("link", { name: "SALON ECLAT SARL" })).toHaveAttribute("href", "#/prospects/21");
  });
});
