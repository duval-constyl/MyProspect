import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect } from "react";
import { describe, expect, it, vi } from "vitest";

import type { MapViewProps } from "../components/MapView";
import { mockApi } from "../test/mockApi";
import MapPage from "./MapPage";

// The real map needs WebGL: it is replaced by a fake that reports a fixed view.
vi.mock("../components/MapView", () => ({
  default: function FakeMapView({ onViewChange }: MapViewProps) {
    useEffect(() => {
      onViewChange({ bbox: [4.8, 45.7, 4.9, 45.8], zoom: 12.6, center: { lat: 45.75, long: 4.85 } });
    }, [onViewChange]);
    return <div data-testid="map" />;
  },
}));

const STATS = { in_view: 12, with_site: 5, without_site: 7 };

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MapPage pollMs={10} />
    </QueryClientProvider>,
  );
}

describe("MapPage", () => {
  it("test_shows_counters_from_stats", async () => {
    const { requests } = mockApi({
      "GET /prospects/stats": { body: STATS },
      "GET /prospects/clusters": { body: { clusters: [] } },
    });

    renderPage();

    expect(await screen.findByText("Dans la vue : 12")).toBeInTheDocument();
    expect(screen.getByText("Avec site : 5")).toBeInTheDocument();
    expect(screen.getByText("Sans site : 7")).toBeInTheDocument();
    const stats = requests.find((r) => r.path === "/prospects/stats")!;
    expect(stats.query.get("bbox")).toBe("4.8,45.7,4.9,45.8");
    const clusters = requests.find((r) => r.path === "/prospects/clusters")!;
    expect(clusters.query.get("zoom")).toBe("12");
  });

  it("test_offer_selector_changes_cluster_query", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi({
      "GET /prospects/stats": { body: STATS },
      "GET /prospects/clusters": { body: { clusters: [] } },
    });
    renderPage();
    await screen.findByText("Dans la vue : 12");
    expect(requests.find((r) => r.path === "/prospects/clusters")!.query.get("offer")).toBe("web");

    await user.selectOptions(screen.getByLabelText("Offre affichée"), "Mobile");

    await waitFor(() =>
      expect([...requests].reverse().find((r) => r.path === "/prospects/clusters")!.query.get("offer")).toBe("mobile"),
    );
  });

  it("test_start_collection_posts_selected_naf_codes", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi({
      "GET /prospects/stats": { body: STATS },
      "GET /prospects/clusters": { body: { clusters: [] } },
      "POST /zones/collect": { status: 202, body: { job_id: 7 } },
      "GET /jobs/7": { body: { state: "done", done: 0, total: 0, error: null } },
    });
    renderPage();

    await user.type(screen.getByLabelText("Commune (nom ou code INSEE)"), "Villeurbanne");
    await user.click(screen.getByLabelText("Coiffure (96.02A)"));
    await user.click(screen.getByLabelText("Garage (45.20A)"));
    await user.click(screen.getByRole("button", { name: "Lancer la récolte" }));

    await waitFor(() => expect(requests.some((r) => r.method === "POST")).toBe(true));
    const post = requests.find((r) => r.method === "POST")!;
    expect(post.path).toBe("/zones/collect");
    expect(post.body).toEqual({
      kind: "commune",
      geojson: { commune: "Villeurbanne" },
      naf_codes: ["45.20A", "96.02A"],
    });
  });

  it("test_circle_tab_posts_map_centre_and_radius", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi({
      "GET /prospects/stats": { body: STATS },
      "GET /prospects/clusters": { body: { clusters: [] } },
      "POST /zones/collect": { status: 202, body: { job_id: 8 } },
      "GET /jobs/8": { body: { state: "done", done: 0, total: 0, error: null } },
    });
    renderPage();

    await user.click(screen.getByRole("tab", { name: "Cercle" }));
    const radius = screen.getByLabelText("Rayon (km)");
    await user.clear(radius);
    await user.type(radius, "3");
    await user.click(screen.getByLabelText("Plomberie (43.22A)"));
    await user.click(screen.getByRole("button", { name: "Lancer la récolte" }));

    await waitFor(() => expect(requests.some((r) => r.method === "POST")).toBe(true));
    expect(requests.find((r) => r.method === "POST")!.body).toEqual({
      kind: "circle",
      geojson: {
        type: "Feature",
        geometry: { type: "Point", coordinates: [4.85, 45.75] },
        properties: { radius_km: 3 },
      },
      naf_codes: ["43.22A"],
    });
  });

  it("test_progress_bar_follows_job_until_done", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi({
      "GET /prospects/stats": { body: STATS },
      "GET /prospects/clusters": { body: { clusters: [] } },
      "POST /zones/collect": { status: 202, body: { job_id: 7 } },
      "GET /jobs/7": [
        { body: { state: "running", done: 1, total: 3, error: null } },
        { body: { state: "running", done: 2, total: 3, error: null } },
        { body: { state: "done", done: 3, total: 3, error: null } },
      ],
    });
    renderPage();

    await user.type(screen.getByLabelText("Commune (nom ou code INSEE)"), "Lyon");
    await user.click(screen.getByLabelText("Garage (45.20A)"));
    await user.click(screen.getByRole("button", { name: "Lancer la récolte" }));

    expect(await screen.findByText("Récolte en cours : 1 / 3")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("value", "1");
    expect(await screen.findByText("Récolte terminée : 3 entreprises.")).toBeInTheDocument();
    const jobPolls = requests.filter((r) => r.path === "/jobs/7").length;
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(requests.filter((r) => r.path === "/jobs/7").length).toBe(jobPolls); // polling stopped
    // The map counters are refreshed once the collection is over.
    expect(requests.filter((r) => r.path === "/prospects/stats").length).toBeGreaterThan(1);
  });

  it("test_error_message_shown_when_zone_too_large", async () => {
    const user = userEvent.setup();
    mockApi({
      "GET /prospects/stats": { body: STATS },
      "GET /prospects/clusters": { body: { clusters: [] } },
      "POST /zones/collect": {
        status: 422,
        body: { detail: "Zone trop grande : 63 km de large, 50 km maximum." },
      },
    });
    renderPage();

    await user.type(screen.getByLabelText("Commune (nom ou code INSEE)"), "Arles");
    await user.click(screen.getByLabelText("Garage (45.20A)"));
    await user.click(screen.getByRole("button", { name: "Lancer la récolte" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Zone trop grande : 63 km de large, 50 km maximum.",
    );
  });

  it("test_requires_a_trade_before_posting", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi({
      "GET /prospects/stats": { body: STATS },
      "GET /prospects/clusters": { body: { clusters: [] } },
    });
    renderPage();

    await user.type(screen.getByLabelText("Commune (nom ou code INSEE)"), "Lyon");
    await user.click(screen.getByRole("button", { name: "Lancer la récolte" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Choisissez au moins un métier.");
    expect(requests.some((r) => r.method === "POST")).toBe(false);
  });

  it("test_failed_job_shows_its_message", async () => {
    const user = userEvent.setup();
    mockApi({
      "GET /prospects/stats": { body: STATS },
      "GET /prospects/clusters": { body: { clusters: [] } },
      "POST /zones/collect": { status: 202, body: { job_id: 9 } },
      "GET /jobs/9": {
        body: {
          state: "failed",
          done: 1,
          total: 1,
          error: "Récolte interrompue : Registre des entreprises indisponible (HTTP 500) pour la page 2.",
        },
      },
    });
    renderPage();

    await user.type(screen.getByLabelText("Commune (nom ou code INSEE)"), "Lyon");
    await user.click(screen.getByLabelText("Garage (45.20A)"));
    await user.click(screen.getByRole("button", { name: "Lancer la récolte" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Registre des entreprises indisponible");
  });
});
