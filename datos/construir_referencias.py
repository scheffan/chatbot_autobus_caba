"""Baja de OpenStreetMap los lugares que sirven de referencia al dar indicaciones.

Monumentos, plazas, estaciones, hospitales, bancos, shoppings, museos…
Así el bot puede decir "frente al Obelisco" o "cerca del Banco Nación".

Uso:
    python datos/construir_referencias.py web/datos/referencias.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request

SERVIDORES = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
CAJA = "-34.95,-58.75,-34.40,-58.20"  # sur, oeste, norte, este

# (filtro de Overpass, tipo que guardamos)
FILTROS = [
    ('["historic"~"^(monument|memorial)$"]', "monumento"),
    ('["tourism"~"^(attraction|museum)$"]', "atraccion"),
    ('["leisure"="park"]', "plaza"),
    ('["place"="square"]', "plaza"),
    ('["station"="subway"]', "subte"),
    ('["railway"="station"]', "estacion"),
    ('["amenity"="hospital"]', "hospital"),
    ('["amenity"="university"]', "universidad"),
    ('["amenity"="bank"]', "banco"),
    ('["shop"="mall"]', "shopping"),
    ('["leisure"="stadium"]', "estadio"),
    ('["amenity"="theatre"]', "teatro"),
]


def consulta() -> str:
    partes = []
    for filtro, _ in FILTROS:
        partes.append(f'nwr{filtro}["name"]({CAJA});')
    return f"[out:json][timeout:180];({''.join(partes)});out center tags;"


def tipo_de(etiquetas: dict) -> str:
    for filtro, tipo in FILTROS:
        clave, _, valor = filtro.strip('[]').partition("=") if "=" in filtro and "~" not in filtro else filtro.strip('[]').partition("~")
        clave = clave.strip('"')
        valor = valor.strip('"').strip("^$()")
        opciones = valor.split("|")
        if etiquetas.get(clave) in opciones:
            return tipo
    return "lugar"


MASCULINOS = {"hospital", "teatro", "estadio", "shopping", "banco", "sanatorio", "museo", "monumento",
              "centro", "colegio", "parque", "instituto", "cementerio", "palacio", "mercado", "obelisco"}
FEMENINOS = {"universidad", "plaza", "plazoleta", "clínica", "facultad", "estación", "torre", "iglesia",
             "basílica", "catedral", "biblioteca", "casa", "galería"}


def con_articulo(nombre: str) -> str:
    """'Hospital Fernández' -> 'el Hospital Fernández', 'Plaza de Mayo' -> 'la Plaza de Mayo'."""
    primera = nombre.split(" ", 1)[0].lower()
    if primera in MASCULINOS:
        return f"el {nombre}"
    if primera in FEMENINOS:
        return f"la {nombre}"
    return nombre


def nombre_lindo(etiquetas: dict, tipo: str) -> str:
    nombre = etiquetas.get("name", "").strip()
    if tipo == "banco":
        # La marca dice más que el nombre de la sucursal: "Banco Nación".
        nombre = (etiquetas.get("brand") or "").strip() or nombre
        if not nombre.lower().startswith("banco"):
            nombre = f"el banco {nombre}"
    elif tipo == "subte" and "estación" not in nombre.lower():
        return f"la estación {nombre} del subte"
    elif tipo == "estacion" and "estación" not in nombre.lower():
        return f"la estación {nombre}"
    elif tipo in ("monumento", "atraccion") and " " not in nombre:
        return f"el {nombre}"
    return con_articulo(nombre)


def bajar() -> dict:
    datos = urllib.parse.urlencode({"data": consulta()}).encode()
    ultimo_error = None
    for servidor in SERVIDORES:
        for intento in range(3):
            try:
                pedido = urllib.request.Request(servidor, data=datos, headers={"User-Agent": "bondi-caba/1.0 (github.com/scheffan/chatbot_autobus_caba)"})
                with urllib.request.urlopen(pedido, timeout=240) as respuesta:
                    return json.load(respuesta)
            except Exception as error:  # noqa: BLE001
                ultimo_error = error
                print(f"Falló {servidor} ({error}), reintento…", file=sys.stderr)
                time.sleep(10 * (intento + 1))
    raise SystemExit(f"No pude bajar los datos de OpenStreetMap: {ultimo_error}")


def procesar(osm: dict) -> list:
    lugares = []
    vistos = set()
    for e in osm.get("elements", []):
        etiquetas = e.get("tags", {})
        lat = e.get("lat") or e.get("center", {}).get("lat")
        lon = e.get("lon") or e.get("center", {}).get("lon")
        if lat is None or lon is None or not etiquetas.get("name"):
            continue
        tipo = tipo_de(etiquetas)
        # Bustos y placas con nombre de persona no sirven para ubicarse:
        # de monumentos y atracciones solo dejamos los conocidos (con Wikidata).
        if tipo in ("monumento", "atraccion") and not etiquetas.get("wikidata"):
            continue
        nombre = nombre_lindo(etiquetas, tipo)
        clave = (nombre.lower(), round(lat, 3), round(lon, 3))
        if clave in vistos:
            continue
        vistos.add(clave)
        lugares.append([round(lat, 6), round(lon, 6), nombre, tipo])
    return lugares


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("salida")
    args = parser.parse_args(argv)
    lugares = procesar(bajar())
    with open(args.salida, "w", encoding="utf-8") as f:
        json.dump(lugares, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(lugares)} lugares -> {args.salida}", file=sys.stderr)


if __name__ == "__main__":
    main()
