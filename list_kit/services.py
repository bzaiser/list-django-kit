from .models import ListTemplate


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
    {"key": "use_image", "label": "Bild-URL", "icon": "bi-image", "desc": "Titel- oder Vorschaubild", "default_zone": "body"},
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
    ]
    created_or_existing = []
    for item in defaults:
        slug = item["slug"]
        defaults_dict = {k: v for k, v in item.items() if k != "slug"}
        obj, _ = ListTemplate.objects.using(db_alias).get_or_create(slug=slug, defaults=defaults_dict)
        created_or_existing.append(obj)
    return created_or_existing
