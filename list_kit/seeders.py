from django.contrib.auth import get_user_model
from seed_kit.registry import register_seeder

from .models import Collection, Entry
from .services import seed_default_templates


def seed_list_demo(count: int = 4):
    User = get_user_model()
    owner = User.objects.filter(is_staff=True).first() or User.objects.first()
    if owner is None:
        return 0

    tpl_map = {t.slug: t for t in seed_default_templates()}
    news_col, _ = Collection.objects.get_or_create(
        slug="news",
        defaults={
            "title": "Aktuelles & News",
            "template": tpl_map["news-aktuelles"],
            "owner": owner,
            "responsible_user": owner,
            "is_public": True,
        },
    )
    faq_col, _ = Collection.objects.get_or_create(
        slug="faq",
        defaults={
            "title": "Häufige Fragen (FAQ)",
            "template": tpl_map["faq"],
            "owner": owner,
            "responsible_user": owner,
            "is_public": True,
        },
    )

    created = 0
    for i in range(max(1, min(5, count))):
        title = f"Neuigkeit #{i + 1}: Willkommen im neuen Portal"
        if not Entry.objects.filter(collection=news_col, title=title).exists():
            Entry.objects.create(
                collection=news_col,
                title=title,
                notes="Kurze Beispiel-Meldung aus dem Demo-Seeder.",
                visibility="public",
                created_by=owner,
            )
            created += 1

    faq_title = "Wie kann ich mich für einen Kurs anmelden?"
    if not Entry.objects.filter(collection=faq_col, title=faq_title).exists():
        Entry.objects.create(
            collection=faq_col,
            title=faq_title,
            notes="Einfach unter Termine auf 'Jetzt anmelden' klicken und das Formular absenden.",
            visibility="public",
            created_by=owner,
        )
        created += 1

    return created


def reset_list_demo():
    Entry.objects.filter(notes="Kurze Beispiel-Meldung aus dem Demo-Seeder.").delete()


register_seeder("list_kit", seed_list_demo, order=40, reset_fn=reset_list_demo)
