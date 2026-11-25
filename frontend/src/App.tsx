import { useEffect, useState } from "react";

import MapPage from "./pages/MapPage";

/** Tiny hash router: #/ (carte). Pages are added as the plan's tasks deliver them. */
function useHashRoute(): string {
  const [hash, setHash] = useState(window.location.hash || "#/");
  useEffect(() => {
    const onChange = () => setHash(window.location.hash || "#/");
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return hash;
}

const LINKS = [{ href: "#/", label: "Carte" }];

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
      <main className="content">
        <MapPage />
      </main>
    </div>
  );
}
