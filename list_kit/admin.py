from django.contrib import admin

from .models import Collection, Entry, ListTemplate


@admin.register(ListTemplate)
class ListTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "content_type", "is_system", "updated_at")
    list_filter = ("content_type", "is_system")
    search_fields = ("name", "slug")


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ("title", "template", "owner", "is_public", "created_at")
    list_filter = ("template", "is_public")
    search_fields = ("title", "slug")


@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    list_display = ("title", "collection", "status", "visibility", "is_completed", "is_pinned", "created_at")
    list_filter = ("visibility", "is_completed", "is_pinned")
    search_fields = ("title", "notes")
