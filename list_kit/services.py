import html
import re

from django.db.models import Q
from django.utils import timezone

from .models import Entry, ListTemplate


FIELD_DEFS = [
    {"key": "use_notes", "label": "Notizen / Text", "icon": "bi-card-text", "desc": "Freitext oder Beschreibung", "default_zone": "body"},
    {"key": "use_rich_notes", "label": "WYSIWYG-Text (Notizen)", "icon": "bi-textarea-t", "desc": "Formatierter Text-Editor (Fett, Listen, Links) für Notizen", "default_zone": "body"},
    {"key": "use_status", "label": "Status-Auswahl", "icon": "bi-tag", "desc": "Eigene Statuswerte (Offen, Erledigt...)", "default_zone": "header"},
    {"key": "use_start_date", "label": "Startdatum", "icon": "bi-calendar-event", "desc": "Beginn / Startzeitpunkt", "default_zone": "body"},
    {"key": "use_end_date", "label": "Enddatum / Frist", "icon": "bi-flag", "desc": "Fälligkeits- oder Enddatum", "default_zone": "body"},
    {"key": "use_reminder", "label": "Erinnerung", "icon": "bi-alarm", "desc": "Erinnerungs-Zeitpunkt", "default_zone": "body"},
    {"key": "use_amount", "label": "Menge & Einheit", "icon": "bi-123", "desc": "Zählwert mit optionaler Einheit", "default_zone": "footer"},
    {"key": "use_price", "label": "Preis / Betrag", "icon": "bi-currency-euro", "desc": "Geldbetrag in €", "default_zone": "footer"},
    {"key": "use_rating", "label": "Bewertung (1–5)", "icon": "bi-star", "desc": "Sterne-Bewertung", "default_zone": "footer"},
    {"key": "use_url", "label": "Link / Seitenverweis", "icon": "bi-link-45deg", "desc": "Verweis auf eigene Seite oder externen Link (öffnet extern im neuen Tab)", "default_zone": "footer"},
    {"key": "use_cover_image", "label": "Titelbild / Einzelbild", "icon": "bi-image", "desc": "Positionierbares Hauptbild (links/rechts/oben/unten) unabhängig von der Galerie", "default_zone": "body"},
    {"key": "use_image", "label": "Fotos / Bildanhang", "icon": "bi-images", "desc": "Bild-URL oder Mehrfach-Foto-Upload", "default_zone": "body"},
    {"key": "use_image_checklist", "label": "Fotos einzeln abhakbar", "icon": "bi-check2-square", "desc": "Hochgeladene Fotos mit Textzeile abhaken", "default_zone": "body"},
    {"key": "use_location", "label": "Ort / Raum", "icon": "bi-geo-alt", "desc": "Ortsangabe", "default_zone": "body"},
    {"key": "use_category", "label": "Kategorie (Stammdaten)", "icon": "bi-folder2-open", "desc": "Vorgefilterte Kategorie aus domain_kit", "default_zone": "header"},
    {"key": "use_master_status", "label": "Status (Stammdaten)", "icon": "bi-bookmark-check", "desc": "Zentraler Status aus domain_kit", "default_zone": "header"},
    {"key": "use_person", "label": "Person / Kontakt", "icon": "bi-person-badge", "desc": "Verknüpfung zu Person aus domain_kit", "default_zone": "body"},
    {"key": "use_document", "label": "Dokumente / Downloads", "icon": "bi-file-earmark-arrow-down", "desc": "Datei-Upload oder öffentliches Dokument zum Download", "default_zone": "footer"},
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
            "allowed_statuses_json": [
                {"key": "open", "label": "Offen", "completes": False},
                {"key": "confirmed", "label": "Bestätigt", "completes": False},
                {"key": "cancelled", "label": "Abgesagt", "completes": False},
            ],
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
            "allowed_statuses_json": [
                {"key": "open", "label": "Offen", "completes": False},
                {"key": "confirmed", "label": "Bestätigt", "completes": False},
                {"key": "attended", "label": "Teilgenommen", "completes": False},
                {"key": "cancelled", "label": "Abgesagt", "completes": False},
            ],
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
            "allowed_statuses_json": [
                {"key": "open", "label": "Offen", "completes": False},
                {"key": "confirmed", "label": "Bestätigt", "completes": False},
                {"key": "cancelled", "label": "Abgesagt", "completes": False},
            ],
            "custom_fields_json": [
                {"key": "vorname", "label": "Vorname", "type": "text", "options": "", "zone": "header", "show_on_card": True},
                {"key": "nachname", "label": "Nachname", "type": "text", "options": "", "zone": "header", "show_on_card": True},
                {"key": "absender_email", "label": "E-Mail", "type": "email", "options": "", "zone": "body", "show_on_card": True},
                {"key": "telefon", "label": "Telefon", "type": "text", "options": "", "zone": "body", "show_on_card": False},
                {"key": "strasse", "label": "Straße & Hausnummer", "type": "text", "options": "", "zone": "body", "show_on_card": False},
                {"key": "plz_ort", "label": "PLZ / Ort", "type": "text", "options": "", "zone": "body", "show_on_card": False},
                {"key": "portal_zugang", "label": "Portal-Zugang gewünscht?", "type": "select", "options": "Ja, Nein", "zone": "body", "show_on_card": True},
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
            "allowed_statuses_json": [
                {"key": "open", "label": "Offen", "completes": False},
                {"key": "confirmed", "label": "Bestätigt", "completes": False},
                {"key": "cancelled", "label": "Abgesagt", "completes": False},
            ],
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
            "allowed_statuses_json": [
                {"key": "open", "label": "Offen", "completes": False},
                {"key": "confirmed", "label": "Bestätigt", "completes": False},
                {"key": "cancelled", "label": "Abgesagt", "completes": False},
            ],
            "custom_fields_json": [
                {"key": "absender_name", "label": "Name (optional)", "type": "text", "options": "", "zone": "header", "show_on_card": True},
                {"key": "absender_email", "label": "E-Mail-Adresse", "type": "email", "options": "", "zone": "header", "show_on_card": True},
                {"key": "themen", "label": "Interessen / Themen", "type": "text", "options": "", "zone": "body", "show_on_card": False},
            ],
            "is_system": True,
        },
        {
            "slug": "fotoalbum",
            "name": "Fotoalbum / Impressionen",
            "icon": "bi-images",
            "content_type": "list",
            "description": "Bildergalerie & Impressionen für Veranstaltungen und die Webseite.",
            "use_notes": True,
            "use_image": True,
            "use_start_date": True,
            "ui_style_json": {"layout_mode": "cards", "card_width": "1/3", "density": "normal"},
            "is_system": True,
        },
        {
            "slug": "protokoll",
            "name": "Sitzungsprotokoll & Beschlüsse",
            "icon": "bi-journal-check",
            "content_type": "list",
            "description": "Vorstands- & Mitgliederversammlungs-Protokolle inkl. Beschlüsse & PDF-Export.",
            "use_notes": True,
            "use_start_date": True,
            "use_location": True,
            "custom_fields_json": [
                {"key": "sitzungsart", "label": "Sitzungsart", "type": "select", "options": "Vorstandssitzung, Mitgliederversammlung, Beirat", "zone": "header", "show_on_card": True},
                {"key": "anwesende", "label": "Anwesende / Teilnehmer", "type": "text", "options": "", "zone": "header", "show_on_card": True},
                {"key": "beschluss", "label": "Gefasster Beschluss", "type": "text", "options": "", "zone": "body", "show_on_card": True},
                {"key": "abstimmung", "label": "Abstimmung (Ja / Nein / Enth.)", "type": "text", "options": "", "zone": "body", "show_on_card": True},
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


_ALLOWED_RICH_TAGS = {
    "p", "br", "strong", "b", "em", "i", "u", "s", "ul", "ol", "li",
    "h1", "h2", "h3", "h4", "blockquote", "a", "span", "div", "font",
    "img", "hr", "table", "thead", "tbody", "tr", "th", "td",
}
_VOID_RICH_TAGS = {"br", "hr", "img"}
_STRIP_RICH_VOID_TAGS = {"embed"}
_STRIP_RICH_CONTENT_TAGS = {"script", "style", "iframe", "object", "svg", "form"}
_ALLOWED_RICH_STYLES = {
    "color", "background-color", "text-align", "font-weight", "font-style",
    "text-decoration", "max-width", "width", "height", "border-radius",
}


def _sanitize_rich_style(raw_style: str) -> str:
    safe_parts = []
    for decl in (raw_style or "").split(";"):
        if ":" not in decl:
            continue
        prop, val = decl.split(":", 1)
        prop_l = prop.strip().lower()
        val_s = val.strip()
        if prop_l not in _ALLOWED_RICH_STYLES or not val_s or "\\" in val_s:
            continue
        val_l = val_s.lower()
        if any(bad in val_l for bad in ("url(", "expression(", "javascript:", "@import")):
            continue
        safe_parts.append(f"{prop_l}: {val_s}")
    return "; ".join(safe_parts)


def sanitize_rich_html(raw_html: str) -> str:
    """Allow safe WYSIWYG formatting tags while stripping scripts and event handlers."""
    if not raw_html:
        return ""
    from html.parser import HTMLParser

    class _Parser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.out = []
            self._skip = 0

        def handle_starttag(self, tag, attrs):
            t = tag.lower()
            if t in _STRIP_RICH_VOID_TAGS:
                return
            if t in _STRIP_RICH_CONTENT_TAGS:
                self._skip += 1
                return
            if self._skip > 0 or t not in _ALLOWED_RICH_TAGS:
                return
            clean = []
            for k, v in attrs:
                kl = (k or "").lower()
                if kl == "class" and v:
                    sc = re.sub(r"[^A-Za-z0-9 _-]", "", v).strip()
                    if sc:
                        clean.append(f'class="{html.escape(sc, quote=True)}"')
                elif kl == "style" and v:
                    ss = _sanitize_rich_style(v)
                    if ss:
                        clean.append(f'style="{html.escape(ss, quote=True)}"')
                elif t == "font" and kl == "color" and v:
                    ss = _sanitize_rich_style(f"color: {v}")
                    if ss:
                        clean.append(f'style="{html.escape(ss, quote=True)}"')
                elif t == "a" and kl == "href" and v:
                    vl = v.strip()
                    if vl.lower().startswith(("http://", "https://", "mailto:", "tel:", "#")) or (vl.startswith("/") and not vl.startswith("//")):
                        clean.append(f'href="{html.escape(vl, quote=True)}"')
                elif t == "a" and kl == "target" and v in ("_blank", "_self"):
                    clean.append(f'target="{v}"')
                elif t == "img" and kl == "src" and v:
                    vl = v.strip()
                    if vl.lower().startswith(("http://", "https://", "data:image/")) or (vl.startswith("/") and not vl.startswith("//")):
                        clean.append(f'src="{html.escape(vl, quote=True)}"')
                elif t == "img" and kl == "alt" and v is not None:
                    clean.append(f'alt="{html.escape(v, quote=True)}"')
            attr_str = (" " + " ".join(clean)) if clean else ""
            self.out.append(f"<{t}{attr_str}>")

        def handle_endtag(self, tag):
            t = tag.lower()
            if t in _STRIP_RICH_CONTENT_TAGS:
                if self._skip > 0:
                    self._skip -= 1
                return
            if self._skip > 0 or t not in _ALLOWED_RICH_TAGS or t in _VOID_RICH_TAGS:
                return
            self.out.append(f"</{t}>")

        def handle_data(self, data):
            if self._skip == 0:
                self.out.append(html.escape(data, quote=False))

        def handle_entityref(self, name):
            if self._skip == 0:
                self.out.append(f"&{name};")

        def handle_charref(self, name):
            if self._skip == 0:
                self.out.append(f"&#{name};")

    p = _Parser()
    p.feed(raw_html)
    p.close()
    return "".join(p.out).strip()


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


def get_archived_entries(content_type: str | None = "news", year: int | None = None, limit: int | None = None):
    """Return expired/archived public Entry objects across public collections."""
    now = timezone.now()
    qs = (
        Entry.objects.select_related("collection", "collection__template", "created_by")
        .filter(collection__is_public=True, visibility="public", expires_at__isnull=False, expires_at__lte=now)
    )
    if content_type:
        qs = qs.filter(collection__template__content_type=content_type)
    if year:
        qs = qs.filter(Q(publish_at__year=year) | Q(publish_at__isnull=True, created_at__year=year))
    qs = qs.order_by("-publish_at", "-created_at")
    if limit is not None:
        return list(qs[:limit])
    return list(qs)


def get_site_page_choices() -> list[dict]:
    """Return internal website routes & published PublicPage items from site_kit if installed."""
    pages: list[dict] = []
    try:
        from django.apps import apps
        if not apps.is_installed("site_kit"):
            return pages
        from site_kit.models import PublicPage
        for p in PublicPage.objects.filter(is_published=True).order_by("-is_home", "menu_order", "title"):
            url = "/" if p.is_home else f"/seite/{p.slug}/"
            pages.append({"url": url, "label": p.title})
        for std_url, std_label in (("/news/", "News (Übersicht)"), ("/termine/", "Termine (Übersicht)"), ("/programm/", "Jahresprogramm")):
            if not any(x["url"] == std_url for x in pages):
                pages.append({"url": std_url, "label": std_label})
    except Exception:
        return pages
    return pages


def get_domain_masterdata_choices(content_type: str = "list", public_only: bool = False) -> dict:
    """Safely load master data choices from domain_kit when installed."""
    res = {"categories": [], "statuses": [], "persons": [], "documents": []}
    try:
        from django.apps import apps
        if not apps.is_installed("domain_kit"):
            return res
        from domain_kit.models import Category, Document, Person, Status
    except Exception:
        return res

    purpose_map = {
        "news": ["news", "general", "all", ""],
        "inventory": ["inventory", "asset", "general", "all", ""],
        "contact": ["person", "contact", "general", "all", ""],
        "photo_gallery": ["gallery", "media", "news", "general", "all", ""],
    }
    allowed_purposes = purpose_map.get(content_type, [content_type, "general", "all", ""])
    try:
        cat_qs = Category.objects.all()
        if hasattr(Category, "is_active"):
            cat_qs = cat_qs.filter(is_active=True)
        filtered_cats = list(cat_qs.filter(purpose__in=allowed_purposes).order_by("name"))
        if not filtered_cats:
            filtered_cats = list(cat_qs.order_by("name"))
        res["categories"] = [{"id": c.id, "name": c.name} for c in filtered_cats]
    except Exception:
        pass

    try:
        st_qs = Status.objects.all()
        if hasattr(Status, "is_active"):
            st_qs = st_qs.filter(is_active=True)
        res["statuses"] = [{"id": s.id, "name": s.name} for s in st_qs.order_by("name")]
    except Exception:
        pass

    try:
        p_qs = Person.objects.all()
        if hasattr(Person, "is_active"):
            p_qs = p_qs.filter(is_active=True)
        if public_only and hasattr(Person, "is_public"):
            p_qs = p_qs.filter(is_public=True)
        res["persons"] = [{"id": p.id, "name": p.full_name} for p in p_qs.order_by("last_name", "first_name")[:200]]
    except Exception:
        pass

    try:
        d_qs = Document.objects.exclude(file="").exclude(file__isnull=True)
        if public_only:
            d_qs = d_qs.filter(is_public=True)
        res["documents"] = [
            {"id": d.id, "title": d.title, "is_public": bool(getattr(d, "is_public", False))}
            for d in d_qs.order_by("-created_at")[:150]
        ]
    except Exception:
        pass

    return res


def get_linked_domain_document(doc_id, require_public: bool = False) -> dict | None:
    """Resolve a linked domain_kit.Document into a safe download dict."""
    if not doc_id:
        return None
    try:
        from django.apps import apps
        if not apps.is_installed("domain_kit"):
            return None
        from domain_kit.models import Document
        qs = Document.objects.filter(pk=int(doc_id))
        if require_public:
            qs = qs.filter(is_public=True)
        doc = qs.first()
        if not doc or not doc.file:
            return None
        return {"id": doc.id, "title": doc.title, "url": doc.file.url, "is_public": bool(doc.is_public)}
    except Exception:
        return None


def get_gallery_photos(collection_slug: str | None = None, limit: int = 60) -> list[dict]:
    """Return public EntryImage items from public collections for site_kit photo galleries."""
    from .models import EntryImage

    qs = (
        EntryImage.objects.select_related("entry", "entry__collection")
        .filter(entry__collection__is_public=True, entry__visibility="public")
        .order_by("-entry__is_pinned", "-entry__created_at", "id")
    )
    if collection_slug:
        qs = qs.filter(entry__collection__slug=collection_slug)
    photos = []
    for img in qs[:limit]:
        try:
            url = img.image.url
        except Exception:
            url = ""
        if not url:
            continue
        photos.append({
            "id": img.id,
            "url": url,
            "caption": img.caption or img.entry.title,
            "entry_title": img.entry.title,
            "notes": (img.entry.notes or "").strip(),
            "has_custom_caption": bool((img.caption or "").strip()),
        })
    return photos


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
