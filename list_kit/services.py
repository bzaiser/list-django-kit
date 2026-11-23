import html
import re

from django.db.models import Q
from django.utils import timezone

from .models import Entry, ListTemplate


FIELD_DEFS = [
    {"key": "use_notes", "label": "Notizen / Text", "icon": "bi-card-text", "desc": "Freitext oder Beschreibung", "default_zone": "body"},
    {"key": "use_status", "label": "Status-Auswahl", "icon": "bi-tag", "desc": "Eigene Statuswerte (Offen, Erledigt...)", "default_zone": "header"},
    {"key": "use_start_date", "label": "Startdatum", "icon": "bi-calendar-event", "desc": "Beginn / Startzeitpunkt", "default_zone": "body"},
    {"key": "use_end_date", "label": "Enddatum / Frist", "icon": "bi-flag", "desc": "Fälligkeits- oder Enddatum", "default_zone": "body"},
    {"key": "use_reminder", "label": "Erinnerung", "icon": "bi-alarm", "desc": "Erinnerungs-Zeitpunkt", "default_zone": "body"},
    {"key": "use_amount", "label": "Menge & Einheit", "icon": "bi-123", "desc": "Zählwert mit optionaler Einheit", "default_zone": "footer"},
    {"key": "use_price", "label": "Preis / Betrag", "icon": "bi-currency-euro", "desc": "Geldbetrag in €", "default_zone": "footer"},
    {"key": "use_rating", "label": "Bewertung (1–5)", "icon": "bi-star", "desc": "Sterne-Bewertung", "default_zone": "footer"},
    {"key": "use_url", "label": "URL / Link", "icon": "bi-link-45deg", "desc": "Externer Link", "default_zone": "footer"},
    {"key": "use_image", "label": "Fotos / Bildanhang", "icon": "bi-images", "desc": "Bild-URL oder Mehrfach-Foto-Upload", "default_zone": "body"},
    {"key": "use_image_checklist", "label": "Fotos einzeln abhakbar", "icon": "bi-check2-square", "desc": "Hochgeladene Fotos mit Textzeile abhaken", "default_zone": "body"},
    {"key": "use_location", "label": "Ort / Raum", "icon": "bi-geo-alt", "desc": "Ortsangabe", "default_zone": "body"},
]


def seed_default_templates(db_alias: str = "default") -> list[ListTemplate]:
    defaults = [
        {
            "slug": "aufgabenliste",
            "name": "Aufgabenliste",
            "icon": "bi-check2-square",
            "content_type": "list",
            "description": "Klassische Aufgaben- und To-Do-Liste mit Fristen.",
            "use_notes": True,
            "use_status": True,
            "use_end_date": True,
            "is_system": True,
        },
        {
            "slug": "news-aktuelles",
            "name": "News & Aktuelles",
            "icon": "bi-newspaper",
            "content_type": "news",
            "description": "Redaktionelle Beiträge und Meldungen für interne & öffentliche Bereiche.",
            "use_notes": True,
            "use_status": True,
            "use_image": True,
            "use_url": True,
            "custom_fields_json": [
                {"key": "teaser", "label": "Teaser", "type": "text", "options": "", "zone": "body", "show_on_card": True},
                {"key": "kategorie", "label": "Kategorie", "type": "text", "options": "", "zone": "header", "show_on_card": True},
            ],
            "is_system": True,
        },
        {
            "slug": "faq",
            "name": "FAQ",
            "icon": "bi-question-circle",
            "content_type": "faq",
            "description": "Häufig gestellte Fragen mit Antworten.",
            "use_notes": True,
            "use_status": False,
            "custom_fields_json": [
                {"key": "kategorie", "label": "Bereich", "type": "text", "options": "", "zone": "header", "show_on_card": True},
            ],
            "is_system": True,
        },
        {
            "slug": "kontakt-anfragen",
            "name": "Kontakt & Anfragen",
            "icon": "bi-inbox",
            "content_type": "form_inbox",
            "description": "Öffentliches Kontakt- oder Antragsformular mit Benachrichtigung.",
            "use_notes": True,
            "use_status": True,
            "custom_fields_json": [
                {"key": "absender_name", "label": "Name", "type": "text", "options": "", "zone": "header", "show_on_card": True},
                {"key": "absender_email", "label": "E-Mail", "type": "text", "options": "", "zone": "body", "show_on_card": True},
            ],
            "is_system": True,
        },
        {
            "slug": "kurs-anmeldung",
            "name": "Kurs- & Veranstaltungsanmeldung",
            "icon": "bi-calendar-check",
            "content_type": "form_inbox",
            "description": "Online-Anmeldung für Kurse & Veranstaltungen mit Bestätigung durch Verantwortliche.",
            "use_notes": True,
            "use_status": True,
            "use_amount": True,
            "custom_fields_json": [
                {"key": "absender_name", "label": "Name", "type": "text", "options": "", "zone": "header", "show_on_card": True},
                {"key": "absender_email", "label": "E-Mail", "type": "email", "options": "", "zone": "body", "show_on_card": True},
                {"key": "telefon", "label": "Telefon", "type": "text", "options": "", "zone": "body", "show_on_card": False},
                {"key": "kurs_termin", "label": "Kurs / Veranstaltung", "type": "text", "options": "", "zone": "header", "show_on_card": True},
            ],
            "is_system": True,
        },
        {
            "slug": "mitgliedsantrag",
            "name": "Mitgliedsantrag",
            "icon": "bi-person-plus",
            "content_type": "form_inbox",
            "description": "Öffentlicher Aufnahmeantrag für neue Mitglieder mit Bestätigung.",
            "use_notes": True,
            "use_status": True,
            "custom_fields_json": [
                {"key": "vorname", "label": "Vorname", "type": "text", "options": "", "zone": "header", "show_on_card": True},
                {"key": "nachname", "label": "Nachname", "type": "text", "options": "", "zone": "header", "show_on_card": True},
                {"key": "absender_email", "label": "E-Mail", "type": "email", "options": "", "zone": "body", "show_on_card": True},
                {"key": "telefon", "label": "Telefon", "type": "text", "options": "", "zone": "body", "show_on_card": False},
                {"key": "strasse", "label": "Straße & Hausnummer", "type": "text", "options": "", "zone": "body", "show_on_card": False},
                {"key": "plz_ort", "label": "PLZ / Ort", "type": "text", "options": "", "zone": "body", "show_on_card": False},
            ],
            "is_system": True,
        },
        {
            "slug": "kuendigung",
            "name": "Kündigung / Abmeldung",
            "icon": "bi-person-dash",
            "content_type": "form_inbox",
            "description": "Kündigung der Mitgliedschaft oder Abmeldung mit Bestätigung.",
            "use_notes": True,
            "use_status": True,
            "use_end_date": True,
            "custom_fields_json": [
                {"key": "absender_name", "label": "Name", "type": "text", "options": "", "zone": "header", "show_on_card": True},
                {"key": "absender_email", "label": "E-Mail", "type": "email", "options": "", "zone": "body", "show_on_card": True},
                {"key": "wunschdatum", "label": "Kündigung zum", "type": "date", "options": "", "zone": "body", "show_on_card": True},
            ],
            "is_system": True,
        },
        {
            "slug": "newsletter-abo",
            "name": "Newsletter-Abo",
            "icon": "bi-envelope-check",
            "content_type": "form_inbox",
            "description": "Anmeldung zum Newsletter mit Bestätigung & Export.",
            "use_notes": False,
            "use_status": True,
            "custom_fields_json": [
                {"key": "absender_name", "label": "Name (optional)", "type": "text", "options": "", "zone": "header", "show_on_card": True},
                {"key": "absender_email", "label": "E-Mail-Adresse", "type": "email", "options": "", "zone": "header", "show_on_card": True},
                {"key": "themen", "label": "Interessen / Themen", "type": "text", "options": "", "zone": "body", "show_on_card": False},
            ],
            "is_system": True,
        },
    ]
    created_or_existing = []
    for item in defaults:
        slug = item["slug"]
        defaults_dict = {k: v for k, v in item.items() if k != "slug"}
        obj, _ = ListTemplate.objects.using(db_alias).get_or_create(slug=slug, defaults=defaults_dict)
        created_or_existing.append(obj)
    return created_or_existing


def render_safe_markdown(text: str) -> str:
    """Render minimal, XSS-safe Markdown (headings, bold, italic, links, lists, paragraphs)."""
    if not text:
        return ""
    escaped = html.escape(text, quote=True)

    def _inline(line: str) -> str:
        line = re.sub(
            r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
            r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>',
            line,
        )
        line = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", line)
        line = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", line)
        return line

    out = []
    in_list = False
    for raw_line in escaped.splitlines():
        line = raw_line.strip()
        if not line:
            if in_list:
                out.append("</ul>")
                in_list = False
            continue
        if line.startswith("### "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f'<h5 class="fw-bold mt-3 mb-2">{_inline(line[4:])}</h5>')
        elif line.startswith("## "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f'<h4 class="fw-bold mt-3 mb-2">{_inline(line[3:])}</h4>')
        elif line.startswith("- ") or line.startswith("* "):
            if not in_list:
                out.append('<ul class="mb-2">')
                in_list = True
            out.append(f"<li>{_inline(line[2:])}</li>")
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f'<p class="mb-2">{_inline(line)}</p>')
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def get_published_entries(content_type: str | None = None, collection_slug: str | None = None, limit: int | None = None):
    """Return currently published public Entry objects across public collections."""
    now = timezone.now()
    qs = (
        Entry.objects.select_related("collection", "collection__template", "created_by")
        .filter(collection__is_public=True, visibility="public")
        .filter(Q(publish_at__isnull=True) | Q(publish_at__lte=now))
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
    )
    if content_type:
        qs = qs.filter(collection__template__content_type=content_type)
    if collection_slug:
        qs = qs.filter(collection__slug=collection_slug)
    qs = qs.order_by("-is_pinned", "-publish_at", "-created_at")
    if limit is not None:
        return list(qs[:limit])
    return list(qs)


def notify_staff_submission(collection, entry) -> None:
    """Notify collection owner and staff via notify_kit when a public form is submitted."""
    try:
        from django.contrib.auth import get_user_model
        from notify_kit.services import notify
    except Exception:
        return

    User = get_user_model()
    recipients = set()
    if getattr(collection, "responsible_user_id", None):
        recipients.add(collection.responsible_user)
    if collection.owner_id:
        recipients.add(collection.owner)
    for u in User.objects.filter(is_active=True, is_staff=True):
        recipients.add(u)

    for u in recipients:
        try:
            notify(
                user=u,
                title=f"Neuer Eingang: {entry.title}",
                message=f"Über Formular „{collection.title}“ eingereicht.",
                level="info",
                link=f"/lists/{collection.id}/",
                topic="list_kit.submission",
            )
        except Exception:
            pass
