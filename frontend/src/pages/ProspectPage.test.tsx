import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ScoreCard from "../components/ScoreCard";
import { mockApi } from "../test/mockApi";
import type { ProspectDetail } from "../types";
import ProspectPage from "./ProspectPage";

const WEB_PRIORITY = {
  value: 51,
  reasons: [
    { code: "opportunity", label: "Opportunité 50/100, comptée pour moitié", points: 25 },
    { code: "phone", label: "Téléphone connu", points: 12 },
    { code: "small_structure", label: "Petite structure : décideur facile à joindre", points: 8 },
    { code: "nearby", label: "À 4 km de chez vous", points: 6 },
  ],
};

const DETAIL: ProspectDetail = {
  id: 1,
  siret: "11111111100011",
  name: "SALON ECLAT",
  naf: "96.02A",
  effectif_code: "01",
  created_on: "2015-03-01",
  address: "12 RUE DE LA REPUBLIQUE 69001 LYON",
  city: "LYON",
  lat: 45.76,
  long: 4.83,
  is_individual: false,
  opposed_to_prospecting: false,
  first_seen_at: "2026-11-25T09:00:00Z",
  last_collected_at: "2026-11-25T09:00:00Z",
  contacts: [
    { kind: "phone", value: "04 78 00 00 01", source: "osm", seen_on: "2026-11-20" },
    { kind: "website", value: "https://salon-eclat.fr", source: "osm", seen_on: "2026-11-20" },
  ],
  site_analysis: {
    url: "https://salon-eclat.fr/",
    reachable: true,
    https: false,
    has_title: true,
    has_description: false,
    has_h1: true,
    has_viewport: false,
    response_ms: 320,
    tech: ["wordpress"],
    mobile_perf: null,
    analyzed_at: "2026-11-25T09:00:00Z",
  },
  scores: [
    {
      offer: "web",
      value: 50,
      tier: 3,
      reasons: [
        { code: "no_https", label: "Site sans HTTPS (connexion non sécurisée)", points: 20 },
        { code: "missing_seo_tags", label: "Balises de référencement manquantes : description", points: 15 },
        { code: "no_viewport", label: "Site non adapté au mobile (pas de balise viewport)", points: 15 },
      ],
    },
    {
      offer: "mobile",
      value: 70,
      tier: 5,
      reasons: [
        { code: "no_online_booking", label: "Aucune réservation ni prise de rendez-vous en ligne détectée", points: 50 },
        { code: "no_online_order", label: "Aucune commande en ligne détectée", points: 20 },
      ],
    },
    { offer: "cloud", value: 0, tier: 1, reasons: [] },
  ],
  priority: WEB_PRIORITY,
  priority_by_offer: {
    web: WEB_PRIORITY,
    mobile: {
      value: 61,
      reasons: [
        { code: "opportunity", label: "Opportunité 70/100, comptée pour moitié", points: 35 },
        { code: "phone", label: "Téléphone connu", points: 12 },
        { code: "small_structure", label: "Petite structure : décideur facile à joindre", points: 8 },
        { code: "nearby", label: "À 4 km de chez vous", points: 6 },
      ],
    },
    cloud: {
      value: 26,
      reasons: [
        { code: "phone", label: "Téléphone connu", points: 12 },
        { code: "small_structure", label: "Petite structure : décideur facile à joindre", points: 8 },
        { code: "nearby", label: "À 4 km de chez vous", points: 6 },
      ],
    },
  },
  tracking: { status: "new", favorite: false, notes: "", updated_at: null },
};

function renderPage(id = 1) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProspectPage id={id} />
    </QueryClientProvider>,
  );
}

describe("ProspectPage", () => {
  it("test_score_card_lists_every_reason", () => {
    render(<ScoreCard score={DETAIL.scores[0]} />);

    expect(screen.getByText("50")).toBeInTheDocument();
    expect(screen.getByText("Palier 3 / 6")).toBeInTheDocument();
    const reasons = screen.getAllByRole("listitem");
    expect(reasons).toHaveLength(3);
    for (const reason of DETAIL.scores[0].reasons) {
      expect(screen.getByText(reason.label)).toBeInTheDocument();
    }
    expect(within(reasons[0]).getByText("+20")).toBeInTheDocument();
  });

  it("test_score_card_without_reason_says_so", () => {
    render(<ScoreCard score={{ offer: "web", value: 0, tier: 1, reasons: [] }} />);

    expect(screen.getByText("Aucun défaut relevé.")).toBeInTheDocument();
  });

  it("test_contact_shows_source_and_date", async () => {
    mockApi({ "GET /prospects/1": { body: DETAIL } });

    renderPage();

    const phone = (await screen.findByText("04 78 00 00 01")).closest("li")!;
    expect(within(phone).getByText("Téléphone")).toBeInTheDocument();
    expect(within(phone).getByText("Source : OpenStreetMap")).toBeInTheDocument();
    expect(within(phone).getByText("vu le 20/11/2026")).toBeInTheDocument();
  });

  it("test_copy_button_copies_the_value", async () => {
    const user = userEvent.setup();
    mockApi({ "GET /prospects/1": { body: DETAIL } });
    renderPage();

    const phone = (await screen.findByText("04 78 00 00 01")).closest("li")!;
    await user.click(within(phone).getByRole("button", { name: "Copier" }));

    expect(await navigator.clipboard.readText()).toBe("04 78 00 00 01");
  });

  it("test_no_contacts_shows_message_instead_of_empty_block", async () => {
    mockApi({ "GET /prospects/1": { body: { ...DETAIL, contacts: [], site_analysis: null } } });

    renderPage();

    expect(await screen.findByText("Aucune coordonnée connue pour cette entreprise.")).toBeInTheDocument();
    expect(screen.getByText("Aucune analyse de site : pas de site connu.")).toBeInTheDocument();
  });

  it("test_shows_identity_priority_and_site_analysis", async () => {
    mockApi({ "GET /prospects/1": { body: DETAIL } });

    renderPage();

    expect(await screen.findByRole("heading", { name: "SALON ECLAT" })).toBeInTheDocument();
    expect(screen.getByText(/11111111100011/)).toBeInTheDocument();
    expect(screen.getByText("Priorité Web : 51")).toBeInTheDocument();
    expect(screen.getAllByText("Téléphone connu").length).toBeGreaterThan(0);
    expect(screen.getByText("HTTPS : non")).toBeInTheDocument();
    expect(screen.getByText("Technologies : wordpress")).toBeInTheDocument();
    expect(screen.queryByText("Opposée à la prospection commerciale")).not.toBeInTheDocument();
  });

  it("test_profile_shows_three_score_cards", async () => {
    mockApi({ "GET /prospects/1": { body: DETAIL } });

    renderPage();

    expect(await screen.findByRole("region", { name: "Score Web" })).toBeInTheDocument();
    const mobile = screen.getByRole("region", { name: "Score Mobile" });
    expect(within(mobile).getByText("70")).toBeInTheDocument();
    expect(within(mobile).getByText("Aucune commande en ligne détectée")).toBeInTheDocument();
    const cloud = screen.getByRole("region", { name: "Score Cloud et logiciel" });
    expect(within(cloud).getByText("Aucun défaut relevé.")).toBeInTheDocument();
    expect(screen.getByText("Priorité Web : 51")).toBeInTheDocument();
    expect(screen.getByText("Priorité Mobile : 61")).toBeInTheDocument();
    expect(screen.getByText("Priorité Cloud et logiciel : 26")).toBeInTheDocument();
  });

  it("test_opposed_company_shows_warning", async () => {
    mockApi({ "GET /prospects/1": { body: { ...DETAIL, opposed_to_prospecting: true } } });

    renderPage();

    expect(await screen.findByText(/Opposée à la prospection commerciale/)).toBeInTheDocument();
  });

  it("test_status_change_sends_patch", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi({
      "GET /prospects/1": { body: DETAIL },
      "PATCH /prospects/1/tracking": {
        body: { status: "contacted", favorite: false, notes: "", updated_at: "2026-11-25T10:00:00Z" },
      },
    });
    renderPage();

    await user.selectOptions(await screen.findByLabelText("Statut"), "Contacté");

    await waitFor(() => expect(requests.some((r) => r.method === "PATCH")).toBe(true));
    expect(requests.find((r) => r.method === "PATCH")!.body).toEqual({ status: "contacted" });
  });

  it("test_notes_and_favorite_are_saved", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi({
      "GET /prospects/1": { body: DETAIL },
      "PATCH /prospects/1/tracking": { body: DETAIL.tracking },
    });
    renderPage();

    await user.click(await screen.findByLabelText("Favori"));
    await user.type(screen.getByLabelText("Notes"), "Rappeler lundi");
    await user.click(screen.getByRole("button", { name: "Enregistrer les notes" }));

    await waitFor(() => expect(requests.filter((r) => r.method === "PATCH")).toHaveLength(2));
    const patches = requests.filter((r) => r.method === "PATCH").map((r) => r.body);
    expect(patches).toEqual([{ favorite: true }, { notes: "Rappeler lundi" }]);
  });

  it("test_delete_asks_confirmation_before_calling_api", async () => {
    const user = userEvent.setup();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { requests } = mockApi({
      "GET /prospects/1": { body: DETAIL },
      "DELETE /prospects/1": { status: 204 },
    });
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Supprimer définitivement" }));
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(requests.some((r) => r.method === "DELETE")).toBe(false);

    confirm.mockReturnValue(true);
    await user.click(screen.getByRole("button", { name: "Supprimer définitivement" }));
    await waitFor(() => expect(requests.some((r) => r.method === "DELETE")).toBe(true));
    await waitFor(() => expect(window.location.hash).toBe("#/prospects"));
  });

  it("test_do_not_contact_button_calls_api", async () => {
    const user = userEvent.setup();
    const { requests } = mockApi({
      "GET /prospects/1": { body: DETAIL },
      "POST /prospects/1/do-not-contact": {
        body: { status: "refused", favorite: false, notes: "", updated_at: "2026-11-25T10:00:00Z" },
      },
    });
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Ne plus contacter" }));

    await waitFor(() =>
      expect(requests.some((r) => r.method === "POST" && r.path === "/prospects/1/do-not-contact")).toBe(true),
    );
  });

  it("test_unknown_prospect_shows_message", async () => {
    mockApi({ "GET /prospects/9": { status: 404, body: { detail: "Prospect introuvable." } } });

    renderPage(9);

    expect(await screen.findByRole("alert")).toHaveTextContent("Prospect introuvable.");
  });
});
