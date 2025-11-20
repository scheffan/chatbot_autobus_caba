import os
import httpx
from typing import Optional, Tuple

CITY = os.getenv("CITY_NAME", "").strip() or "CABA"

# Bounding box de CABA aprox (lon, lat): left, top, right, bottom
# Nominatim usa: viewbox=left,top,right,bottom  y bounded=1 para forzar búsqueda dentro
CABA_VIEWBOX = "-58.531,-34.526,-58.335,-34.705"  # (W, N, E, S)

async def geocode(address: str) -> Optional[Tuple[float, float, str]]:
    """
    Geocodifica con sesgo fuerte a CABA/Argentina.
    - countrycodes=ar limita a Argentina
    - viewbox + bounded limitan a CABA
    - Si el usuario no puso 'CABA', se lo agregamos al query para mejorar el match.
    """
    base = address.strip()
    # si el usuario no puso la ciudad, la agregamos
    if CITY.lower() not in base.lower():
        base = f"{base}, {CITY}"

    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": base,
        "format": "json",
        "limit": 1,
        "addressdetails": 1,
        "countrycodes": "ar",
        "viewbox": CABA_VIEWBOX,
        "bounded": 1,  # respeta el rectángulo
    }
    headers = {"User-Agent": "colectivos-demo-plus"}

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, params=params, headers=headers)
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        x = data[0]
        return float(x["lat"]), float(x["lon"]), x.get("display_name", "")
