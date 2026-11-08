"""Achica el GTFS oficial de colectivos a un JSON liviano para la web y el bot.

El GTFS completo pesa ~1,5 GB (stop_times tiene más de 30 millones de filas).
Acá lo convertimos en "recorridos": cada secuencia distinta de paradas de un
ramal, con el tiempo típico entre paradas y cuántos colectivos pasan por hora.

Uso:
    python datos/construir_red.py colectivos-gtfs.zip web/datos/red.json
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import date

# service_id del GTFS de la Ciudad -> tipo de día.
# Se deduce mirando calendar_dates (qué días de la semana cubre cada servicio).
TIPOS_DE_DIA = ("habil", "sabado", "domingo")
MUESTRAS_DE_TIEMPO = 40


def abrir_csv(archivo: zipfile.ZipFile, nombre: str):
    crudo = archivo.open(nombre)
    texto = io.TextIOWrapper(crudo, encoding="utf-8-sig", newline="")
    return csv.DictReader(texto)


def segundos(hora: str) -> int:
    h, m, s = hora.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def tipos_de_servicio(archivo: zipfile.ZipFile) -> dict[str, str]:
    """Asigna cada service_id a hábil, sábado o domingo según sus fechas.

    Los servicios de feriados (pocas fechas sueltas) se dejan afuera.
    """
    dias: dict[str, Counter] = defaultdict(Counter)
    nombres = set(archivo.namelist())
    if "calendar_dates.txt" in nombres:
        for fila in abrir_csv(archivo, "calendar_dates.txt"):
            if fila.get("exception_type", "1").strip() != "1":
                continue
            f = fila["date"].strip()
            dia = date(int(f[:4]), int(f[4:6]), int(f[6:8])).weekday()
            dias[fila["service_id"].strip()][dia] += 1
    if "calendar.txt" in nombres:
        semana = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        for fila in abrir_csv(archivo, "calendar.txt"):
            for i, d in enumerate(semana):
                if fila.get(d, "0").strip() == "1":
                    dias[fila["service_id"].strip()][i] += 10
    tipos = {}
    for servicio, conteo in dias.items():
        if sum(conteo.values()) < 6:
            # Pocas fechas sueltas: es el servicio de feriados. No lo contamos
            # para no inflar la frecuencia de los días hábiles.
            continue
        habiles = sum(conteo[i] for i in range(5))
        sabados, domingos = conteo[5], conteo[6]
        mayor = max(habiles, sabados, domingos)
        if mayor == habiles and habiles > 0 and habiles >= 2 * max(sabados, domingos, 1) - 1:
            tipos[servicio] = "habil"
        elif mayor == sabados and sabados > 0:
            tipos[servicio] = "sabado"
        else:
            tipos[servicio] = "domingo"
    return tipos


def hacia_donde(cartel: str) -> str:
    """Limpia el cartel del colectivo: "B - a Est. Mitre" -> "Est. Mitre".

    En el GTFS de la Ciudad muchos carteles dicen "a Barracas - IDA" y
    "a Barracas - VUELTA" aunque cada uno va para un lado distinto. En esos
    casos devolvemos "" y el destino se arma con la última parada.
    """
    if re.search(r"-\s*(IDA|VUELTA)\s*$", cartel, re.IGNORECASE):
        return ""
    limpio = re.sub(r"^\s*Ramal\s+\S+?\s*[:-]\s*", "", cartel, flags=re.IGNORECASE)
    limpio = re.sub(r"^\s*[A-ZÑ0-9]{0,2}\s*-\s*", "", limpio)
    limpio = re.sub(r"^\s*[A-ZÑ0-9]{1,2}\s+(?=(?:a|hacia)\s)", "", limpio)
    limpio = re.sub(r"^(?:a|hacia)\s+", "", limpio.strip(), flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", limpio).strip()


def numero_de_linea(nombre_corto: str) -> tuple[str, str]:
    """'24B' -> ('24', 'B'); '505R3' -> ('505', 'R3')."""
    m = re.match(r"^(\d+)(.*)$", nombre_corto.strip())
    if not m:
        return nombre_corto.strip(), ""
    return m.group(1), m.group(2).strip()


class Recorrido:
    __slots__ = ("ruta", "paradas", "suma", "muestras", "frecuencia", "carteles")

    def __init__(self, ruta: str, paradas: tuple[str, ...]):
        self.ruta = ruta
        self.paradas = paradas
        self.suma = [0.0] * len(paradas)
        self.muestras = 0
        self.frecuencia = {t: [0] * 24 for t in TIPOS_DE_DIA}
        self.carteles: Counter = Counter()

    def sumar_viaje(self, tiempos: list[int], tipo: str | None, cartel: str) -> None:
        if tipo:
            hora = (tiempos[0] // 3600) % 24
            self.frecuencia[tipo][hora] += 1
        if cartel:
            self.carteles[cartel] += 1
        if self.muestras < MUESTRAS_DE_TIEMPO:
            inicio = tiempos[0]
            for i, t in enumerate(tiempos):
                self.suma[i] += t - inicio
            self.muestras += 1


def construir(ruta_zip: str, limite: tuple[float, float, float, float] | None = None, avisar=print) -> dict:
    archivo = zipfile.ZipFile(ruta_zip)
    tipos = tipos_de_servicio(archivo)

    rutas = {}
    for fila in abrir_csv(archivo, "routes.txt"):
        linea, ramal = numero_de_linea(fila.get("route_short_name") or "")
        rutas[fila["route_id"].strip()] = {
            "linea": linea,
            "ramal": ramal,
            "nombre": (fila.get("route_long_name") or "").strip(),
            "descripcion": (fila.get("route_desc") or "").strip(),
        }

    viajes = {}
    for fila in abrir_csv(archivo, "trips.txt"):
        viajes[fila["trip_id"].strip()] = (
            fila["route_id"].strip(),
            tipos.get(fila.get("service_id", "").strip()),
            (fila.get("trip_headsign") or "").strip(),
        )
    avisar(f"{len(rutas)} ramales, {len(viajes)} viajes")

    recorridos: dict[tuple, Recorrido] = {}
    vistos: set[str] = set()

    def cerrar(viaje_id, filas):
        if not filas or viaje_id not in viajes:
            return
        filas.sort()
        paradas = tuple(p for _, p, _ in filas)
        tiempos = [t for _, _, t in filas]
        ruta, tipo, cartel = viajes[viaje_id]
        clave = (ruta, paradas)
        rec = recorridos.get(clave)
        if rec is None:
            rec = recorridos[clave] = Recorrido(ruta, paradas)
        rec.sumar_viaje(tiempos, tipo, cartel)

    actual, filas, n = None, [], 0
    for fila in abrir_csv(archivo, "stop_times.txt"):
        viaje = fila["trip_id"]
        if viaje != actual:
            cerrar(actual, filas)
            if actual is not None:
                vistos.add(actual)
            if viaje in vistos:
                raise SystemExit("stop_times.txt no viene agrupado por viaje; hay que ordenarlo antes.")
            actual, filas = viaje, []
        hora = fila.get("departure_time") or fila.get("arrival_time") or ""
        if not hora.strip():
            continue
        filas.append((int(fila["stop_sequence"]), fila["stop_id"].strip(), segundos(hora)))
        n += 1
        if n % 5_000_000 == 0:
            avisar(f"  {n:,} horarios leídos…")
    cerrar(actual, filas)
    avisar(f"{n:,} horarios, {len(recorridos)} recorridos distintos")

    paradas_gtfs = {}
    for fila in abrir_csv(archivo, "stops.txt"):
        lat, lon = float(fila["stop_lat"]), float(fila["stop_lon"])
        if limite and not (limite[0] <= lat <= limite[2] and limite[1] <= lon <= limite[3]):
            continue
        paradas_gtfs[fila["stop_id"].strip()] = (lat, lon, (fila.get("stop_name") or "").strip())

    indice: dict[str, int] = {}
    paradas_salida = []
    recorridos_salida = []
    for rec in recorridos.values():
        # Con un límite geográfico, cortamos el recorrido a las paradas de adentro.
        posiciones = [i for i, p in enumerate(rec.paradas) if p in paradas_gtfs]
        if len(posiciones) < 2 or rec.muestras == 0:
            continue
        ids = []
        for i in posiciones:
            p = rec.paradas[i]
            if p not in indice:
                indice[p] = len(paradas_salida)
                lat, lon, nombre = paradas_gtfs[p]
                paradas_salida.append([round(lat, 6), round(lon, 6), nombre])
            ids.append(indice[p])
        base = rec.suma[posiciones[0]] / rec.muestras
        minutos = [round((rec.suma[i] / rec.muestras - base) / 60, 1) for i in posiciones]
        info = rutas.get(rec.ruta, {"linea": "?", "ramal": "", "nombre": "", "descripcion": ""})
        recorridos_salida.append({
            "linea": info["linea"],
            "ramal": info["ramal"],
            "descripcion": info["descripcion"],
            "hacia": hacia_donde(rec.carteles.most_common(1)[0][0] if rec.carteles else ""),
            "paradas": ids,
            "minutos": minutos,
            "frecuencia": rec.frecuencia,
        })

    recorridos_salida.sort(key=lambda r: (int(r["linea"]) if r["linea"].isdigit() else 9999, r["ramal"]))
    return {
        "version": 1,
        "fuente": "GTFS de colectivos, Buenos Aires Data (Gobierno de la Ciudad de Buenos Aires)",
        "paradas": paradas_salida,
        "recorridos": recorridos_salida,
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("gtfs", help="Archivo .zip del GTFS")
    parser.add_argument("salida", help="Ruta del JSON a generar")
    parser.add_argument("--limite", default="-34.95,-58.75,-34.40,-58.20",
                        help="lat_min,lon_min,lat_max,lon_max. Por defecto CABA y alrededores.")
    args = parser.parse_args(argv)
    limite = tuple(float(x) for x in args.limite.split(",")) if args.limite else None
    red = construir(args.gtfs, limite, avisar=lambda m: print(m, file=sys.stderr))
    with open(args.salida, "w", encoding="utf-8") as f:
        json.dump(red, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(red['paradas'])} paradas y {len(red['recorridos'])} recorridos -> {args.salida}", file=sys.stderr)


if __name__ == "__main__":
    main()
