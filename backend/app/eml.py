"""Draft e-mail files (.eml) to open in the mail client (V3 plan, Task 7).

The file is only written, never sent: the header X-Unsent: 1 makes the mail clients that
support it open the file as a draft, which Duval checks and sends himself.
"""

from email import policy
from email.headerregistry import Address
from email.message import EmailMessage

from app.models import OutreachDraft

AUDIT_FILENAME = "rapport-audit.pdf"
# CRLF line endings and header lines folded under 78 characters, as mail clients expect.
EML_POLICY = policy.default.clone(linesep="\r\n")


def build_eml(
    draft: OutreachDraft,
    to: str,
    sender_name: str,
    sender_email: str,
    audit_pdf: bytes | None = None,
) -> bytes:
    """An unsent e-mail; without `sender_email` the mail client picks its own sender."""
    message = EmailMessage(policy=EML_POLICY)
    message["To"] = to
    if sender_email:
        message["From"] = Address(display_name=sender_name, addr_spec=sender_email)
    message["Subject"] = draft.subject or ""
    message["X-Unsent"] = "1"
    # Quoted-printable keeps the file 7-bit clean while accents and line breaks survive.
    message.set_content(draft.body, cte="quoted-printable")
    if audit_pdf is not None:
        message.add_attachment(audit_pdf, maintype="application", subtype="pdf", filename=AUDIT_FILENAME)
    return message.as_bytes()
