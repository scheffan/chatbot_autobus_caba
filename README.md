# 🚌 Bondi CABA

**¿Qué colectivo me tomo?** Escribís de dónde salís y adónde vas, y te dice qué línea tomar, en qué parada, cada cuánto pasa y dónde bajarte, con referencias para ubicarte ("frente al Obelisco", "cerca del Banco Nación").

- 🌐 **Web:** [scheffan.github.io/chatbot_autobus_caba](https://scheffan.github.io/chatbot_autobus_caba/)
- 💬 **Telegram:** [@bondicaba_bot](https://t.me/bondicaba_bot)

[![Tests](https://github.com/scheffan/chatbot_autobus_caba/actions/workflows/tests.yml/badge.svg)](https://github.com/scheffan/chatbot_autobus_caba/actions/workflows/tests.yml)
[![Publicar](https://github.com/scheffan/chatbot_autobus_caba/actions/workflows/publicar.yml/badge.svg)](https://github.com/scheffan/chatbot_autobus_caba/actions/workflows/publicar.yml)

## Cómo se usa

En Telegram le escribís como le hablarías a alguien:

> quiero ir de Corrientes 800 a Plaza Italia

> cómo llego a Rivadavia 6300 desde Constitución

O le mandás tu ubicación 📍 y después le decís adónde vas. Te contesta algo así:

```
🚌 Del Obelisco a la Plaza Italia

Opción 1: 59 · unos 24 min
🚶 Caminá 2 cuadras hasta la parada de Lavalle 1059.
🚌 Tomá el 59 hacia Int. Cnel. A. Ávalos y D. De Acassuso. Pasa cada 9 min aprox.
⏱️ Viajás 14 minutos (14 paradas) y te bajás en Av. General Las Heras 4273.
🚶 Caminá 1 cuadra hasta la Plaza Italia.
```

Con un botón para ver el recorrido en el mapa de la web.

## Cómo funciona

1. **Datos.** El GTFS oficial de colectivos pesa 1,5 GB (más de 30 millones de horarios). `datos/construir_red.py` lo achica a un JSON de ~4 MB: cada recorrido con sus paradas, el tiempo típico entre ellas y cuántos colectivos pasan por hora en días hábiles, sábados y domingos. `datos/construir_referencias.py` baja de OpenStreetMap monumentos, plazas, estaciones, bancos y otros lugares para usarlos como referencia.
2. **Búsqueda por anillos**, como la Guía T: busca paradas a 300 m de donde estás y de adonde vas; si no alcanza, agranda el anillo a 600, 900 y 1200 m. Arma viajes directos y, si conviene, con un trasbordo caminando hasta otra parada cercana. Suma caminata, espera según la frecuencia de esa hora y viaje, y elige opciones con líneas distintas.
3. **Direcciones.** Primero busca en los lugares conocidos ("Obelisco"), después en el normalizador de direcciones de la Ciudad (USIG, que entiende alturas y esquinas) y por último en Nominatim (OpenStreetMap) para el resto del AMBA.

El mismo buscador (`motor/`) corre en el navegador para la web y en un Worker de Cloudflare para el bot, así que todo es gratis y no hay servidor que mantener.

```
datos/     scripts en Python que arman los JSON (solo biblioteca estándar)
motor/     buscador, textos y geocodificación (JavaScript, sin dependencias)
web/       página con mapa (Leaflet + OpenStreetMap)
worker/    webhook del bot de Telegram (Cloudflare Workers)
tests/     pytest para los datos y node --test para el buscador y el bot
```

## Correrlo en tu compu

Necesitás Python 3.10+ y Node 20+.

```bash
# 1. Bajar el GTFS y armar los datos (tarda unos minutos)
curl -L -o gtfs.zip https://files.mobilitydatabase.org/mdb-1220/latest.zip
mkdir -p web/datos
python datos/construir_red.py gtfs.zip web/datos/red.json
python datos/construir_referencias.py web/datos/referencias.json

# 2. Levantar la web
cp -r motor web/motor
python -m http.server 8000 -d web
# y abrir http://localhost:8000
```

Tests:

```bash
pip install pytest && pytest -q tests/datos
npm test
```

## Publicación

El workflow **Publicar** corre con cada cambio en `main` y todos los lunes: baja el GTFS, arma los datos, publica la web en GitHub Pages y sube el bot a Cloudflare. Para el bot hacen falta dos secretos del repo (*Settings → Secrets and variables → Actions*):

| Secreto | De dónde sale |
| --- | --- |
| `CLOUDFLARE_API_TOKEN` | Cloudflare → *My Profile → API Tokens*, plantilla "Edit Cloudflare Workers" |
| `TELEGRAM_TOKEN` | El token que da [@BotFather](https://t.me/BotFather) |

El workflow conecta solo el webhook de Telegram con el Worker. Sin esos secretos la web se publica igual.

## Sobre los datos

Los recorridos y paradas salen del [GTFS de colectivos de Buenos Aires Data](https://data.buenosaires.gob.ar/dataset/colectivos-gtfs). El último publicado es de **septiembre de 2019**, así que puede haber cambios de recorrido posteriores que no aparezcan. Los tiempos son estimados a partir de los horarios programados, no en tiempo real.

Lugares y mapa: © colaboradores de [OpenStreetMap](https://www.openstreetmap.org/copyright).
