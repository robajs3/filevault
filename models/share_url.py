"""
share_url.py — wspólna logika budowania publicznych linków (share_url) dla
plików, folderów i pokoi.

Dlaczego to nie może być zwykłe url_for(..., _external=True):
FileVault i Koloseum stoją w osobnych kontenerach i komunikują się też po
WEWNĘTRZNEJ sieci Dockera (patrz Koloseum: services/filevault_client.py,
FILEVAULT_INTERNAL_URL). Kiedy request przychodzi tą wewnętrzną drogą,
nagłówek Host to adres kontenerowy (np. host.docker.internal:8000), a
url_for(_external=True) buduje URL właśnie na podstawie Hosta BIEŻĄCEGO
żądania — więc bez PUBLIC_URL share_url wycieka wewnętrzny adres, który
jest bezużyteczny/nieosiągalny dla studenta w przeglądarce.

Jeśli PUBLIC_URL jest ustawiony w konfiguracji — używamy go zawsze,
niezależnie skąd przyszło żądanie. Jeśli nie jest ustawiony — fallback na
url_for(_external=True) (wystarczające, gdy FileVault jest używany tylko
przez przeglądarkę, bez integracji typu Koloseum).
"""
from flask import current_app, url_for


def build_share_url(endpoint: str, **values) -> str:
    public = current_app.config.get("PUBLIC_URL")
    if public:
        path = url_for(endpoint, **values)  # bez _external -> tylko ścieżka
        return f"{public}{path}"
    return url_for(endpoint, _external=True, **values)
