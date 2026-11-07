import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "datos"))

import construir_referencias as cref  # noqa: E402


def test_tipo_de():
    assert cref.tipo_de({"historic": "monument"}) == "monumento"
    assert cref.tipo_de({"station": "subway", "railway": "station"}) == "subte"
    assert cref.tipo_de({"railway": "station"}) == "estacion"
    assert cref.tipo_de({"amenity": "bank"}) == "banco"
    assert cref.tipo_de({"amenity": "cafe"}) == "lugar"


def test_nombre_lindo():
    assert cref.nombre_lindo({"name": "Obelisco"}, "monumento") == "el Obelisco"
    assert cref.nombre_lindo({"name": "Sucursal 23", "brand": "Banco Nación"}, "banco") == "el Banco Nación"
    assert cref.nombre_lindo({"name": "Galicia"}, "banco") == "el banco Galicia"
    assert cref.nombre_lindo({"name": "Carlos Pellegrini"}, "subte") == "la estación Carlos Pellegrini del subte"
    assert cref.nombre_lindo({"name": "Retiro"}, "estacion") == "la estación Retiro"
    assert cref.nombre_lindo({"name": "Plaza de Mayo"}, "plaza") == "la Plaza de Mayo"
    assert cref.nombre_lindo({"name": "Hospital Fernández"}, "hospital") == "el Hospital Fernández"


def test_procesar_saca_repetidos_y_sin_nombre():
    osm = {"elements": [
        {"type": "node", "lat": -34.6037, "lon": -58.3816, "tags": {"name": "Obelisco", "historic": "monument"}},
        {"type": "way", "center": {"lat": -34.60371, "lon": -58.38161}, "tags": {"name": "Obelisco", "historic": "monument"}},
        {"type": "node", "lat": -34.6, "lon": -58.4, "tags": {"amenity": "bank"}},
    ]}
    assert cref.procesar(osm) == [[-34.6037, -58.3816, "el Obelisco", "monumento"]]
