import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { mockApi } from "./test/mockApi";

vi.mock("./components/MapView", () => ({ default: () => null }));

afterEach(() => {
  window.location.hash = "";
});

describe("App", () => {
  it("test_alerts_route_shows_alerts_page_and_nav_link", async () => {
    mockApi({
      "GET /alerts": { body: [] },
      "GET /zones": { body: [] },
      "GET /prospects/duplicates": { body: [] },
    });
    window.location.hash = "#/alertes";
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <App />
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("region", { name: "Alertes" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Navigation principale" });
    expect(screen.getByRole("link", { name: "Alertes", current: "page" })).toHaveAttribute("href", "#/alertes");
    expect(nav).toContainElement(screen.getByRole("link", { name: "Alertes" }));
  });
});
