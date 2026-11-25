import { useState } from "react";

import { CONTACT_KIND_LABELS, SOURCE_LABELS, frenchDate } from "../labels";
import type { Contact } from "../types";

/** Known contact details, each with its source and date. Nothing is sent from here. */
export default function ContactList({ contacts }: { contacts: Contact[] }) {
  const [copied, setCopied] = useState<string | null>(null);

  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(value);
    } catch {
      setCopied(null);
    }
  }

  if (contacts.length === 0) {
    return <p className="hint">Aucune coordonnée connue pour cette entreprise.</p>;
  }
  return (
    <ul className="contacts">
      {contacts.map((contact) => (
        <li key={`${contact.kind}-${contact.value}`}>
          <span className="contact-kind">{CONTACT_KIND_LABELS[contact.kind] ?? contact.kind}</span>
          {contact.kind === "website" ? (
            <a href={/^https?:\/\//.test(contact.value) ? contact.value : `https://${contact.value}`} target="_blank" rel="noopener noreferrer">
              {contact.value}
            </a>
          ) : (
            <span className="contact-value">{contact.value}</span>
          )}
          <span className="hint">Source : {SOURCE_LABELS[contact.source] ?? contact.source}</span>
          <span className="hint">vu le {frenchDate(contact.seen_on)}</span>
          <button type="button" className="secondary" onClick={() => copy(contact.value)}>
            {copied === contact.value ? "Copié" : "Copier"}
          </button>
        </li>
      ))}
    </ul>
  );
}
