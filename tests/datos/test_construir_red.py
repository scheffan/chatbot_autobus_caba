import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "datos"))

import construir_red as cr  # noqa: E402


def escribir_gtfs(ruta: Path) -> Path:
    archivos = {
        "routes.txt": "route_id,route_short_name,route_long_name,route_desc\nR1,24B,Linea 24,Ramal B\nR2,59,Linea 59,\n",
        "trips.txt": "route_id,service_id,trip_id,trip_headsign\n"
                     "R1,SEM,T1,B - a Est. Mitre\nR1,SEM,T2,B - a Est. Mitre\nR1,FER,T3,B - a Est. Mitre\n"
                     "R2,SAB,T4,a Barracas - IDA\n",
        "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\n"
                     "S1,Uno,-34.60,-58.40\nS2,Dos,-34.60,-58.39\nS3,Tres,-34.60,-58.38\nLEJOS,Lejos,-10,-60\n",
        "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
                          "T1,08:00:00,08:00:00,S1,1\nT1,08:05:00,08:05:00,S2,2\nT1,08:12:00,08:12:00,S3,3\n"
                          "T2,08:30:00,08:30:00,S1,1\nT2,08:37:00,08:37:00,S2,2\nT2,08:44:00,08:44:00,S3,3\n"
                          "T3,09:00:00,09:00:00,S1,1\nT3,09:06:00,09:06:00,S2,2\nT3,09:12:00,09:12:00,S3,3\n"
                          "T4,10:00:00,10:00:00,S3,1\nT4,10:10:00,10:10:00,S2,2\nT4,10:20:00,10:20:00,LEJOS,3\n",
        # SEM: dos semanas de lunes a viernes; SAB: varios sábados; FER: un feriado suelto.
        "calendar_dates.txt": "service_id,date,exception_type\n"
                              + "".join(f"SEM,201906{d:02d},1\n" for d in (3, 4, 5, 6, 7, 10, 11, 12, 13, 14))
                              + "".join(f"SAB,201906{d:02d},1\n" for d in (1, 8, 15, 22, 29, 1))
                              + "FER,20190617,1\n",
    }
    with zipfile.ZipFile(ruta, "w") as z:
        for nombre, contenido in archivos.items():
            z.writestr(nombre, contenido)
    return ruta


def test_numero_de_linea():
    assert cr.numero_de_linea("24B") == ("24", "B")
    assert cr.numero_de_linea("505R3") == ("505", "R3")
    assert cr.numero_de_linea("Premetro") == ("Premetro", "")


def test_hacia_donde():
    assert cr.hacia_donde("B - a Est. Mitre") == "Est. Mitre"
    assert cr.hacia_donde("Ramal 2: a Retiro") == "Retiro"
    assert cr.hacia_donde("a Barracas - IDA") == ""
    assert cr.hacia_donde("2 hacia Berazategui") == "Berazategui"
    assert cr.hacia_donde("12 - a Once") == "Once"


def test_construir_red(tmp_path):
    red = cr.construir(str(escribir_gtfs(tmp_path / "gtfs.zip")), (-35, -59, -34, -58), avisar=lambda m: None)
    assert [p[2] for p in red["paradas"]] == ["Uno", "Dos", "Tres"]

    r24 = next(r for r in red["recorridos"] if r["linea"] == "24")
    assert r24["ramal"] == "B"
    assert r24["hacia"] == "Est. Mitre"
    # Tiempo promedio entre paradas (el viaje de feriado también sirve de muestra).
    assert r24["minutos"] == [0, 6.0, 12.7]
    # Los dos viajes de semana salen a las 8; el de feriado no se cuenta.
    assert r24["frecuencia"]["habil"][8] == 2
    assert sum(r24["frecuencia"]["habil"]) == 2
    assert sum(r24["frecuencia"]["domingo"]) == 0

    r59 = next(r for r in red["recorridos"] if r["linea"] == "59")
    # La parada de afuera del límite se recorta.
    assert len(r59["paradas"]) == 2
    assert r59["hacia"] == ""
    assert r59["frecuencia"]["sabado"][10] == 1


def test_main_escribe_json(tmp_path):
    salida = tmp_path / "red.json"
    cr.main([str(escribir_gtfs(tmp_path / "gtfs.zip")), str(salida)])
    datos = json.loads(salida.read_text(encoding="utf-8"))
    assert datos["version"] == 1
    assert len(datos["recorridos"]) == 2
