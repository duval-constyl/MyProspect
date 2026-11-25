import { useEffect, useState } from "react";

import MapPage from "./pages/MapPage";
import ProspectsPage from "./pages/ProspectsPage";

/** Tiny hash router: #/ (carte), #/prospects (liste). */
function useHashRoute(): string {
  const [hash, setHash] = useState(window.location.hash || "#/");
  useEffect(() => {
    const onChange = () => setHash(window.location.hash || "#/");
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return hash;
}

const LINKS = [
  { href: "#/", label: "Carte" },
  { href: "#/prospects", label: "Prospects" },
];

export default function App() {
  const route = useHashRoute();
  return (
    <div className="app">
      <header className="top-bar">
        <span className="brand">MyProspect</span>
        <nav aria-label="Navigation principale">
          {LINKS.map((link) => (
            <a key={link.href} href={link.href} aria-current={route === link.href ? "page" : undefined}>
              {link.label}
            </a>
          ))}
        </nav>
      </header>
      <main className="content">{route === "#/prospects" ? <ProspectsPage /> : <MapPage />}</main>
    </div>
  );
}
