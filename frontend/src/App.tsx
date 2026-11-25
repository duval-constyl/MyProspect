import { useEffect, useState } from "react";

import AlertsPage from "./pages/AlertsPage";
import MapPage from "./pages/MapPage";
import ProspectPage from "./pages/ProspectPage";
import ProspectsPage from "./pages/ProspectsPage";
import TodayPage from "./pages/TodayPage";

/** Tiny hash router: #/ (carte), #/aujourdhui, #/prospects (liste), #/prospects/{id} (fiche), #/alertes. */
function useHashRoute(): string {
  const [hash, setHash] = useState(window.location.hash || "#/");
  useEffect(() => {
    const onChange = () => setHash(window.location.hash || "#/");
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return hash;
}

function isActive(route: string, href: string): boolean {
  return href === "#/" ? route === "#/" : route.startsWith(href);
}

const LINKS = [
  { href: "#/", label: "Carte" },
  { href: "#/aujourdhui", label: "Aujourd'hui" },
  { href: "#/prospects", label: "Prospects" },
  { href: "#/alertes", label: "Alertes" },
];

function Page({ route }: { route: string }) {
  const detail = route.match(/^#\/prospects\/(\d+)$/);
  if (detail) return <ProspectPage key={detail[1]} id={Number(detail[1])} />;
  if (route === "#/prospects") return <ProspectsPage />;
  if (route === "#/aujourdhui") return <TodayPage />;
  if (route === "#/alertes") return <AlertsPage />;
  return <MapPage />;
}

export default function App() {
  const route = useHashRoute();
  return (
    <div className="app">
      <header className="top-bar">
        <span className="brand">MyProspect</span>
        <nav aria-label="Navigation principale">
          {LINKS.map((link) => (
            <a key={link.href} href={link.href} aria-current={isActive(route, link.href) ? "page" : undefined}>
              {link.label}
            </a>
          ))}
        </nav>
      </header>
      <main className="content">
        <Page route={route} />
      </main>
    </div>
  );
}
