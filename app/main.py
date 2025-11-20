# app/main.py
import os, re, math, uuid, pathlib
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from .intents import detect_intent
from .storage import get_conn, get_prefs, upsert_prefs
from .geocode import geocode
from .planner import Planner, haversine

# ======== TTS OFFLINE (SAPI5 via pyttsx3) =========
try:
    import pyttsx3  # Offline, estable en Windows (usa SAPI5)
except ImportError:
    pyttsx3 = None
# ================================================

load_dotenv()
GTFS_SQLITE = os.getenv('GTFS_SQLITE','data/gtfs.sqlite')
APPDATA_SQLITE = os.getenv('APPDATA_SQLITE','data/appdata.sqlite')

# ---- Config TTS desde .env ----
TTS_ENABLED = (os.getenv('TTS_ENABLED', '1') == '1')
TTS_VOICE   = os.getenv('TTS_VOICE', 'es-ES')  # heurística: elegimos la 1ra voz en español disponible
TTS_DIR     = os.getenv('TTS_DIR', 'data/tts')
TTS_RATE    = int(os.getenv('TTS_RATE', '0'))      # 0 = default; valores negativos = más lento; positivos = más rápido
TTS_VOLUME  = float(os.getenv('TTS_VOLUME', '1'))  # 0.0..1.0
pathlib.Path(TTS_DIR).mkdir(parents=True, exist_ok=True)

planner = Planner(GTFS_SQLITE)
conn = get_conn(APPDATA_SQLITE)

app = FastAPI()

# Sesión simple en memoria: últimas opciones y query por usuario
sessions: Dict[str, Dict[str, Any]] = {}  # user_id -> { last_options: [...], last_query: {...} }

# =========================
# Helpers de TTS y respuesta
# =========================

def _pick_spanish_voice(engine) -> Optional[str]:
    """
    Devuelve el id de una voz en español si existe.
    Si TTS_VOICE viene con algo tipo 'es-ES-ElviraNeural' intentamos 'contener'.
    Si no, cualquier voz que diga 'es' / 'spanish' en name o languages.
    """
    target = (TTS_VOICE or "").lower()
    chosen_id = None
    try:
        for v in engine.getProperty("voices"):
            name = (getattr(v, "name", "") or "").lower()
            langs = " ".join([str(x) for x in getattr(v, "languages", [])]) if hasattr(v, "languages") else ""
            llangs = langs.lower()
            # match fuerte: contiene tokens del target
            if target and any(tok and tok in name for tok in target.split("-")):
                chosen_id = v.id
                break
            # match suave: español
            if ("spanish" in name) or ("es" in name) or ("es" in llangs) or ("spa" in llangs):
                if chosen_id is None:
                    chosen_id = v.id
    except Exception:
        pass
    return chosen_id

async def _synth_tts_to_file(text: str) -> str:
    """
    Genera audio WAV offline (pyttsx3/SAPI5) y devuelve /tts/<file>.wav.
    Si TTS no está disponible/activo o falla algo, devuelve "" (no rompe nada).
    """
    if not TTS_ENABLED or not text or not text.strip():
        return ""
    if pyttsx3 is None:
        return ""

    try:
        filename = f"{uuid.uuid4().hex}.wav"
        out_path = pathlib.Path(TTS_DIR) / filename

        eng = pyttsx3.init()  # SAPI5 por defecto en Windows
        # voz
        vid = _pick_spanish_voice(eng)
        if vid:
            try:
                eng.setProperty("voice", vid)
            except Exception:
                pass
        # rate y volumen (opcionales, seguros)
        try:
            if TTS_RATE != 0:
                eng.setProperty("rate", eng.getProperty("rate") + TTS_RATE)
        except Exception:
            pass
        try:
            eng.setProperty("volume", max(0.0, min(1.0, TTS_VOLUME)))
        except Exception:
            pass

        eng.save_to_file(text, str(out_path))
        eng.runAndWait()
        return f"/tts/{filename}"
    except Exception:
        # ante cualquier problema de síntesis, no devolvemos audio pero mantenemos texto
        return ""

async def _reply(text: str) -> JSONResponse:
    """
    Respuesta estándar de la API: siempre 'text' y, si aplica, 'speech_path'.
    Nunca falla aunque TTS explote: devolvemos texto igual.
    """
    speech_path = ""
    try:
        speech_path = await _synth_tts_to_file(text)
    except Exception:
        speech_path = ""
    return JSONResponse({'text': text, 'speech_path': speech_path})

# =========================
# Helpers de texto/formatos
# =========================

def _route_pretty(s: str) -> str:
    if not s: return "?"
    m = re.match(r"^(\d{1,3})\s*([a-zA-Z])?$", s.strip())
    if not m: return s
    num, suf = m.group(1), m.group(2)
    return f"{num} ({suf.upper()})" if suf else num

def _title_like(name: str) -> str:
    if not name: return name
    base = name.strip()
    repl = {
        "Saenz Pena": "Sáenz Peña",
        "Saenz Pe?a": "Sáenz Peña",
        "Jose": "José",
        "Mejia": "Mejía",
        "Inmigrantes": "de los Inmigrantes",
        "Ramos Mejia": "Ramos Mejía",
        "Ramos Mejia Jose Maria": "Ramos Mejía José María",
    }
    for k,v in repl.items():
        base = base.replace(k, v)

    base = re.sub(r"\b(AV|Av|AV\.)\b\.?", "Av.", base)
    base = re.sub(r"\b(DR|Dr|DR\.)\b\.?", "Dr.", base)

    parts = base.split()
    if parts and parts[0].isdigit():
        num = parts[0]
        rest = " ".join(parts[1:])
        base = f"{rest} {num}"

    base = re.sub(r"\b(Av\.)\s*(.*)\s+(Av\.)\b", r"\1 \2", base)

    def tc(word: str) -> str:
        w = word
        lower_words = {"de","del","la","las","los","y","a","al"}
        if w.lower() in lower_words:
            return w.lower()
        if w.lower() in {"av.", "dr."}:
            return w.title()
        return w[:1].upper() + w[1:].lower()

    base = " ".join(tc(w) for w in base.split())
    base = base.replace("Av.", "Av.").replace("Dr.", "Dr.")
    return base.strip()

def _short_place(display_name: str) -> str:
    """
    Normaliza Nominatim a: 'Av. Corrientes 800 · San Nicolás (CABA)'
    """
    if not display_name:
        return ""
    parts = [p.strip() for p in display_name.split(",")]

    calle = None
    altura = None

    for p in parts[:4]:
        pl = p.lower()
        if any(w in pl for w in ["avenida","av.","calle","diag","diagonal","boulevard","bv.","pje","pasaje"]):
            calle = p
        elif p.isdigit():
            altura = p

    if not altura:
        m = re.search(r"\b(\d{2,5})\b", display_name)
        if m:
            altura = m.group(1)

    def norm_calle(c: str) -> str:
        if not c: return c
        c = re.sub(r"\bavenida\b", "Av.", c, flags=re.I)
        c = re.sub(r"\bdiagonal\b", "Diag.", c, flags=re.I)
        c = re.sub(r"\bcalle\b", "Calle", c, flags=re.I)
        return c

    if calle:
        calle = norm_calle(calle)

    barrio = None
    ciudad = None
    for p in reversed(parts):
        pl = p.lower()
        if barrio is None and any(x in pl for x in [
            "san nicolás","retiro","recoleta","palermo","belgrano","caballito","flores",
            "floresta","almagro","boedo","constitución","balvanera","monserrat","san telmo",
            "villa luro","mataderos","velez sarsfield","villa devoto","villa del parque"
        ]):
            barrio = p
        if ciudad is None and any(x in pl for x in ["caba","ciudad autónoma de buenos aires"]):
            ciudad = "CABA"
        if ciudad is None and "buenos aires" in pl:
            ciudad = "Buenos Aires"
        if barrio and ciudad:
            break

    if calle and altura:
        base = f"{calle} {altura}"
    elif calle:
        base = calle
    else:
        base = ", ".join(parts[:2])

    if barrio and ciudad == "CABA":
        return f"{_title_like(base)} · {barrio} (CABA)"
    if barrio:
        return f"{_title_like(base)} · {barrio}"
    if ciudad:
        return f"{_title_like(base)} · {ciudad}"
    return _title_like(base)

def _stop_name(stop_id: str) -> str:
    cur = planner.conn.cursor()
    cur.execute("SELECT stop_name FROM stops WHERE stop_id=? LIMIT 1", (stop_id,))
    r = cur.fetchone()
    return _title_like(r[0]) if r else stop_id


def _transfers_count(opt: dict) -> int:
    if opt.get('type') == 'direct':
        return 0
    legs = opt.get('legs') or []
    return max(1, len(legs)-1)

def _sort_options(options: list) -> list:
    # menos trasbordos -> menor duración -> menos caminata -> menor espera
    return sorted(
        options,
        key=lambda o: (_transfers_count(o),
                       o.get('duration_min', 99999),
                       o.get('walk_m', 99999),
                       o.get('wait_s', 99999))
    )

def _dedupe_semantic(options: list) -> list:
    """Quita duplicados por (línea1, línea2, mid_stop) conservando menor duración."""
    seen = {}
    for o in options:
        if o.get('type') == 'direct':
            k = ("direct", o.get('route_short','').strip())
        else:
            legs = o.get('legs', [])
            r1 = (legs[0].get('route_short','').strip() if legs else "")
            r2 = (legs[-1].get('route_short','').strip() if legs else "")
            mid = o.get('mid_stop','')
            k = (r1, r2, mid)
        best = seen.get(k)
        if not best or o.get('duration_min', 99999) < best.get('duration_min', 99999):
            seen[k] = o
    return list(seen.values())

def _clean_headsign(h: str) -> str:
    # Corrige "hacia a ..." -> "hacia ..."
    return re.sub(r"\bhacia\s+a\b", "hacia ", (h or "").strip(), flags=re.I)

def _route_and_headsign(leg: dict) -> str:
    rs = _route_pretty(leg.get('route_short') or "")
    head = _clean_headsign(leg.get('headsign') or "")
    if head and len(head) <= 40:
        return f"{rs} (hacia {head})"
    return rs

def _format_list(options: list) -> str:
    lines = []
    for i, o in enumerate(options, 1):
        if o.get('type') == 'direct':
            rs = _route_pretty(o.get('route_short') or "")
            head = _clean_headsign(o.get('headsign') or "")
            head_s = f" (hacia {head})" if head else ""
            lines.append(f"Opción {i}: 🚌 {rs}{head_s} — ~{o.get('duration_min')} min")
        else:
            legs = o.get('legs', [])
            if len(legs) >= 2:
                r1 = _route_and_headsign(legs[0])
                r2 = _route_and_headsign(legs[-1])
                mid = o.get('mid_stop') or legs[0].get('to_stop')
                mid_name = _stop_name(mid) if mid else "punto de trasbordo"
                walk = int(o.get('walk_m', 0))
                lines.append(f"Opción {i}: trasbordo: {r1} → {r2} en {mid_name} ({walk} m a pie) — ~{o.get('duration_min')} min")
            else:
                lines.append(f"Opción {i}: 1 trasbordo — ~{o.get('duration_min','?')} min")
    return "\n".join(lines) if lines else "No encontré opciones en este momento."

def _parse_choice(text: str, options: list):
    t = text.lower().strip()
    m = re.search(r'\b([1-9][0-9]?)\b', t)
    if m:
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(options): return idx
    if re.search(r'\b(primera|la primera|uno|la 1|opcion 1|opción 1|la opcion 1|la opción 1)\b', t): return 0
    if re.search(r'\b(segunda|la segunda|dos|la 2|opcion 2|opción 2|la opcion 2|la opción 2)\b', t): return 1
    if re.search(r'\b(tercera|la tercera|tres|la 3|opcion 3|opción 3|la opcion 3|la opción 3)\b', t): return 2
    if any(x in t for x in ["mas rapida","más rápida","la que tarda menos","mas rapido","más rapido","mas rápido"]):
        mins = [o.get('duration_min', 99999) for o in options]
        if mins: return int(min(range(len(mins)), key=lambda i: mins[i]))
    m2 = re.search(r'\b(\d{1,3})\b', t)  # la del 132
    if m2:
        num = m2.group(1)
        for i, o in enumerate(options):
            if o.get('type') == 'direct':
                if (o.get('route_short') or "").startswith(num): return i
            for leg in o.get('legs', []):
                if (leg.get('route_short') or "").startswith(num): return i
    return None

def _detailed_steps(opt: dict, last_query: dict) -> str:
    def dist_to_dest(stop_id: str) -> Optional[int]:
        if not last_query: return None
        dlat, dlon = last_query.get('dest_lat'), last_query.get('dest_lon')
        if dlat is None or dlon is None: return None
        sc = planner.stop_coords(stop_id)
        if not sc: return None
        return int(round(haversine(sc[0], sc[1], dlat, dlon)))

    if opt.get('type') == 'direct':
        rs = _route_pretty(opt.get('route_short') or "")
        head = _clean_headsign(opt.get('headsign') or "")
        o_name = _stop_name(opt.get('orig_stop_id'))
        d_name = _stop_name(opt.get('dest_stop_id'))
        head_s = f" (hacia {head})" if head else ""
        tail = f"Tiempo estimado ~{opt.get('duration_min')} min."
        d2 = dist_to_dest(opt.get('dest_stop_id'))
        if d2 is not None:
            tail += f" Quedás a ~{d2} m de tu destino."
        return (f"🚌 Tomá **{rs}{head_s}** en **{o_name}**. "
                f"Bajate en **{d_name}**. {tail}")

    legs = opt.get('legs', [])
    pasos = [f"🚍 1 trasbordo — estimado ~{opt.get('duration_min')} min"]
    if len(legs) >= 1:
        l1 = legs[0]; rs1 = _route_pretty(l1.get('route_short') or ""); h1 = _clean_headsign(l1.get('headsign') or "")
        desde = _stop_name(l1.get('from_stop','?')); hasta = _stop_name(l1.get('to_stop','?'))
        s1 = f" (hacia {h1})" if h1 else ""
        pasos.append(f"1) Subite al **{rs1}{s1}** en **{desde}** y bajate en **{hasta}**.")
    walk = int(opt.get('walk_m', 0))
    if walk > 0:
        pasos.append(f"2) Caminá ~**{walk} m** hasta la parada del trasbordo.")
    if len(legs) >= 2:
        l2 = legs[1]; rs2 = _route_pretty(l2.get('route_short') or ""); h2 = _clean_headsign(l2.get('headsign') or "")
        desde2 = _stop_name(l2.get('from_stop','?')); hasta2 = _stop_name(l2.get('to_stop','?'))
        idx = 3 if walk > 0 else 2
        s2 = f" (hacia {h2})" if h2 else ""
        d2 = dist_to_dest(l2.get('to_stop'))
        if d2 is not None:
            pasos.append(f"{idx}) Subite al **{rs2}{s2}** en **{desde2}** y bajate en **{hasta2}** (a ~{d2} m de tu destino).")
        else:
            pasos.append(f"{idx}) Subite al **{rs2}{s2}** en **{desde2}** y bajate en **{hasta2}**.")
    if last_query and last_query.get('dest_disp'):
        pasos.append(f"📍 Llegás cerca de **{last_query['dest_disp']}**.")
    return "\n".join(pasos)

# =========================
# Endpoints utilitarios
# =========================

@app.get('/tts/{filename}')
async def get_tts(filename: str):
    fp = pathlib.Path(TTS_DIR) / filename
    if not fp.exists():
        return JSONResponse({'error': 'not found'}, status_code=404)
    # setear mime según extensión
    ext = fp.suffix.lower()
    mime = 'audio/wav' if ext == '.wav' else 'audio/mpeg'
    return FileResponse(str(fp), media_type=mime, filename=filename)

@app.get("/debug/tts")
async def debug_tts():
    info = {
        "pyttsx3_present": pyttsx3 is not None,
        "TTS_ENABLED": TTS_ENABLED,
        "TTS_VOICE": TTS_VOICE,
        "TTS_DIR": TTS_DIR,
    }
    try:
        url = await _synth_tts_to_file("Prueba de voz")
        info["synthesis_ok"] = bool(url)
        info["speech_path"] = url
    except Exception as e:
        info["synthesis_ok"] = False
        info["error"] = f"{type(e).__name__}: {e}"
    return JSONResponse(info)

@app.get("/debug/voices")
async def debug_voices():
    info = {"pyttsx3_present": pyttsx3 is not None, "voices": []}
    try:
        if pyttsx3 is None:
            raise RuntimeError("pyttsx3 no instalado")
        eng = pyttsx3.init()
        for v in eng.getProperty("voices"):
            info["voices"].append({
                "id": v.id,
                "name": getattr(v, "name", ""),
                "languages": [str(x) for x in getattr(v, "languages", [])] if hasattr(v, "languages") else [],
            })
    except Exception as e:
        info["error"] = f"{type(e).__name__}: {e}"
    return JSONResponse(info)

# =========================
# Endpoint principal
# =========================

@app.post('/api/chat')
async def chat(req: Request):
    try:
        body = await req.json()
        user_id = body.get('user_id','anon')
        text_raw = (body.get('text') or '').strip()

        prefs = get_prefs(conn, user_id)
        intent_data = detect_intent(text_raw, prefs=prefs)  # usa reglas + LLM opcional
        intent = intent_data.get("intent","unknown")

        # ---- Elección conversacional de una opción previa ----
        sess = sessions.get(user_id, {})
        last_options = sess.get('last_options', [])
        last_query = sess.get('last_query', {})
        if last_options:
            idx = _parse_choice(text_raw, last_options)
            if idx is not None and 0 <= idx < len(last_options):
                return await _reply(_detailed_steps(last_options[idx], last_query))

        # ---- Mostrar guardados ----
        if intent == 'show_saved':
            which = intent_data.get('which', 'all')
            lines = []
            if which in ('all', 'home'):
                if prefs.get('home_address'):
                    lines.append(f"Casa: {prefs['home_address']}")
                else:
                    lines.append("Casa: (sin guardar)")
            if which in ('all', 'work'):
                if prefs.get('work_address'):
                    lines.append(f"Trabajo: {prefs['work_address']}")
                else:
                    lines.append("Trabajo: (sin guardar)")
            return await _reply("\n".join(lines))

        # ---- Guardar Casa / Trabajo (con o sin “:”) ----
        if intent == 'save_home':
            addr = (intent_data.get('address') or text_raw.split(':',1)[-1]).strip()
            g = await geocode(addr)
            if not g: return await _reply('No pude ubicar esa dirección. Probá con "Calle 123, CABA".')
            lat,lon,disp = g
            upsert_prefs(conn, user_id, home_address=_short_place(disp), home_lat=lat, home_lon=lon)
            return await _reply(f'Guardé tu casa: {_short_place(disp)}.')

        if intent == 'save_work':
            addr = (intent_data.get('address') or text_raw.split(':',1)[-1]).strip()
            g = await geocode(addr)
            if not g: return await _reply('No pude ubicar esa dirección. Probá con "Calle 123, CABA".')
            lat,lon,disp = g
            upsert_prefs(conn, user_id, work_address=_short_place(disp), work_lat=lat, work_lon=lon)
            return await _reply(f'Guardé tu trabajo: {_short_place(disp)}.')

        # ---- Borrar ----
        if intent == 'delete_home':
            upsert_prefs(conn,user_id,home_address=None,home_lat=None,home_lon=None)
            return await _reply('Listo, borré tu casa.')
        if intent == 'delete_work':
            upsert_prefs(conn, user_id, work_address=None, work_lat=None, work_lon=None)
            return await _reply('Listo, borré tu trabajo.')

        # ---- Toggles ----
        if intent == 'faster':
            upsert_prefs(conn, user_id, mode='fast')
            return await _reply('Ok, priorizo llegar más rápido.')
        if intent == 'less_walk':
            upsert_prefs(conn, user_id, mode='walk_min')
            return await _reply('Listo, minimizo caminata.')
        if intent == 'no_transfers':
            upsert_prefs(conn, user_id, mode='balanced')
            return await _reply('Voy a evitar trasbordos cuando se pueda.')

        # ---- Routing (ir de X a Y / de casa a trabajo / etc.) ----
        if intent == 'route':
            origin = intent_data.get('origin')
            dest   = intent_data.get('dest')

            async def resolve_place(name: Optional[str]):
                if not name: return None
                n = (name or "").strip().lower()

                # sinónimos → slots
                HOME_TOKENS = {"home","casa","mi casa"}
                WORK_TOKENS = {"work","trabajo","mi trabajo","laburo","oficina"}

                if n in HOME_TOKENS and prefs.get('home_lat'):
                    return prefs['home_lat'], prefs['home_lon'], prefs['home_address']
                if n in WORK_TOKENS and prefs.get('work_lat'):
                    return prefs['work_lat'], prefs['work_lon'], prefs['work_address']

                # cualquier otra cosa, geocodificamos
                return await geocode(name)

            go = await resolve_place(origin)
            gd = await resolve_place(dest)
            if not go or not gd:
                return await _reply('No pude ubicar origen/destino. Probá con "Corrientes 800, CABA" y "Rivadavia 6300, CABA".')
            lat_o, lon_o, disp_o_full = go
            lat_d, lon_d, disp_d_full = gd

            # === NO re-formatear casa/trabajo: conservar la etiqueta guardada ===
            def _pretty_label(slot_name: Optional[str], raw_disp: str) -> str:
                if (slot_name or "").lower() in ("home", "work"):
                    return raw_disp
                return _short_place(raw_disp)

            disp_o = _pretty_label(intent_data.get('origin'), disp_o_full)
            disp_d = _pretty_label(intent_data.get('dest'),   disp_d_full)

            so = planner.nearest_stops(lat_o, lon_o, limit=6)
            sd = planner.nearest_stops(lat_d, lon_d, limit=6)

            options = []
            # directos primero
            for s1 in so:
                for s2 in sd:
                    options += planner.direct_routes(s1['stop_id'], s2['stop_id'], limit=2)
                    if len(options) >= 3: break
                if len(options) >= 3: break

            # 1 trasbordo con corredor
            if len(options) < 3:
                for s1 in so[:4]:
                    for s2 in sd[:4]:
                        options += planner.one_transfer(
                            s1['stop_id'], s2['stop_id'],
                            max_wait_min=20, walk_radius_m=300,
                            limit=6, allow_two_transfers=False
                        )
                        if len(options) >= 8: break
                    if len(options) >= 8: break

            if not options:
                txt = f"Origen: {disp_o}\nDestino: {disp_d}\n\nNo encontré opciones en este momento.\n\nPodés intentar: Más rápido | Menos caminata | Sin trasbordos"
                return await _reply(txt)

            options = _dedupe_semantic(options)
            options = _sort_options(options)

            sessions[user_id] = {
                'last_options': options,
                'last_query': {
                    'origin_disp': disp_o,
                    'dest_disp': disp_d,
                    'origin_lat': lat_o, 'origin_lon': lon_o,
                    'dest_lat': lat_d, 'dest_lon': lon_d,
                }
            }

            txt = [f"Origen: {disp_o}", f"Destino: {disp_d}", ""]
            txt.append(_format_list(options))
            txt.append("\nDecime: la 1 / la primera / la más rápida / la del 132…")
            return await _reply("\n".join(txt))

        # ---- Próximas salidas / Frecuencia ----
        if intent in ('next_arrivals','frequency'):
            # por defecto usa casa si existe
            base = None
            if prefs.get('home_lat'):
                base = (prefs['home_lat'], prefs['home_lon'], prefs['home_address'])
            if not base:
                return await _reply('Guardá tu casa para buscar próximas salidas cerca. Ej: Guardar casa: Corrientes 800, CABA')
            lat, lon, disp = base
            stops = planner.nearest_stops(lat, lon, limit=1)
            if not stops:
                return await _reply('No encontré paradas cerca. Probá otra esquina.')
            stop = stops[0]
            next3 = planner.next_departures(stop['stop_id'])
            head = planner.headway_estimate(stop['stop_id'])
            lines = [f"Parada: {_title_like(stop['stop_name'])} ({int(stop['distance_m'])} m)"]
            if head:
                lines.append(f"Suele pasar cada {head[0]}–{head[1]} min aprox.")
            if next3:
                hh = ", ".join([x['hm'] + (f" — {x['route_short_name']}" if x.get('route_short_name') else "") for x in next3])
                lines.append(f"Próximas: {hh}")
            return await _reply("\n".join(lines))

        # ---- Fallback ----
        return await _reply('Decime: ir de <origen> a <destino>. Ej: ir de Corrientes 800 a Rivadavia 6300.')

    except Exception as e:
        # Anti-crash: devolvemos texto con el nombre del error en vez de 500,
        # y dejamos traza en consola para debug.
        try:
            import traceback; traceback.print_exc()
        except Exception:
            pass
        return JSONResponse({"text": f"Ocurrió un error: {e.__class__.__name__}", "speech_path": ""}, status_code=200)

# Static web
app.mount('/', StaticFiles(directory='web', html=True), name='web')
