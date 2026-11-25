import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockApi } from "../test/mockApi";
import TodayPage from "./TodayPage";

const TODAY = {
  followups_due: [
    { id: 7, prospect_id: 1, prospect_name: "SALON ECLAT", phone: "04 78 00 00 01", due_on: "2026-11-20", note: "Rappeler pour le devis" },
    { id: 8, prospect_id: 2, prospect_name: "GARAGE MARTIN", phone: null, due_on: "2026-11-25", note: "" },
  ],
  top_priority: [
    { id: 3, name: "PLOMBERIE DURAND", city: "LYON", phone: "04 78 00 00 03", best_offer: "mobile", score: 70, priority: 61, status: "new" },
    { id: 4, name: "AGENCE DU PARC", city: null, phone: null, best_offer: "web", score: 75, priority: 44, status: "to_contact" },
  ],
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TodayPage />
    </QueryClientProvider>,
  );
}

describe("TodayPage", () => {
  it("test_today_page_lists_followups_and_top_prospects", async () => {
    mockApi({ "GET /today": { body: TODAY } });

    renderPage();

    const followups = await screen.findByRole("region", { name: "Relances du jour" });
    const first = within(followups).getByText("SALON ECLAT").closest("li")!;
    expect(within(first).getByText("20/11/2026")).toBeInTheDocument();
    expect(within(first).getByText("Rappeler pour le devis")).toBeInTheDocument();
    expect(within(first).getByText("04 78 00 00 01")).toBeInTheDocument();
    expect(within(followups).getByRole("link", { name: "SALON ECLAT" })).toHaveAttribute("href", "#/prospects/1");

    const top = screen.getByRole("region", { name: "À contacter en priorité" });
    const row = within(top).getByText("PLOMBERIE DURAND").closest("tr")!;
    expect(within(row).getByText("Mobile")).toBeInTheDocument();
    expect(within(row).getByText("61")).toBeInTheDocument();
    const second = within(top).getByText("AGENCE DU PARC").closest("tr")!;
    expect(second.querySelector("td[data-column='phone']")!.textContent).toBe("—");
  });

  it("test_marking_a_followup_done_calls_the_api_and_refreshes", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi({
      "GET /today": [{ body: TODAY }, { body: { ...TODAY, followups_due: TODAY.followups_due.slice(1) } }],
      "POST /followups/7/done": { body: { id: 7, prospect_id: 1, due_on: "2026-11-20", note: "", done_at: "2026-11-25T10:00:00Z" } },
    });
    renderPage();

    const first = (await screen.findByText("Rappeler pour le devis")).closest("li")!;
    await user.click(within(first).getByRole("button", { name: "Fait" }));

    await waitFor(() => expect(requests.some((r) => r.method === "POST" && r.path === "/followups/7/done")).toBe(true));
    await waitFor(() => expect(screen.queryByText("Rappeler pour le devis")).not.toBeInTheDocument());
  });

  it("test_empty_day_says_so", async () => {
    mockApi({ "GET /today": { body: { followups_due: [], top_priority: [] } } });

    renderPage();

    expect(await screen.findByText("Aucune relance pour aujourd'hui.")).toBeInTheDocument();
    expect(screen.getByText(/Aucun prospect à contacter/)).toBeInTheDocument();
  });
});
