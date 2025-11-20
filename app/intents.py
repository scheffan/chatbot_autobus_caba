# app/intents.py
import os, re
from typing import Dict, Any, Optional

# --- Utilidad mínima para normalizar espacios/acentos raros ---
def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()

# --- Detección por reglas livianas (rápida y robusta) ---
def _rule_based(text: str, prefs: Dict[str, Any]) -> Dict[str, Any]:
    t = _norm(text)

    # =========== Selección de opción (la 1 / opcion 2 / la primera / la más rápida / la del 132) ===========
    if re.search(r"\b(opcion|opción)\s*([1-9])\b", t):
        n = int(re.search(r"\b(opcion|opción)\s*([1-9])\b", t).group(2))
        return {"intent": "choose_option", "choice": n}
    if re.search(r"\b(la\s*)?primera\b", t):
        return {"intent": "choose_option", "choice": 1}
    if re.search(r"\b(la\s*)?segunda\b", t):
        return {"intent": "choose_option", "choice": 2}
    if re.search(r"\b(la\s*)?tercera\b", t):
        return {"intent": "choose_option", "choice": 3}
    if re.search(r"\bla\s*([1-9])\b", t):
        return {"intent": "choose_option", "choice": int(re.search(r"\bla\s*([1-9])\b", t).group(1))}
    if re.fullmatch(r"[1-9]", t):
        return {"intent": "choose_option", "choice": int(t)}
    # "la más rápida", "la que tarda menos"
    if any(x in t for x in ["mas rapida", "más rapida", "más rápida", "mas rápida", "la que tarda menos", "mas rapido", "más rapido", "más rápido", "mas rápido"]):
        return {"intent": "choose_option", "choice": 0}  # se resolverá a la más corta en el backend

    # =========== Mostrar datos guardados ===========
    if (
        re.search(r"\b(ver|mostrar|mis\s*datos|datos guardados)\b", t)
        or t in ("ver casa", "ver trabajo", "ver mis datos", "mis datos")
    ):
        which = "all"
        if "ver casa" in t: which = "home"
        if "ver trabajo" in t: which = "work"
        return {"intent": "show_saved", "which": which}

    # =========== Guardar casa/trabajo (aceptar "guardar/guarda/guardá") ===========
    # ejemplos: "guardar casa av corrientes 800", "guarda casa corrientes 800", "guardá trabajo rivadavia 6300", "mi casa es ..."
    m = re.search(r"\b(guardar|guarda|guardá)\s+casa[:\s]+(.+)$", t)
    if m: return {"intent": "save_home", "address": m.group(2).strip()}
    m = re.search(r"\b(guardar|guarda|guardá)\s+trabajo[:\s]+(.+)$", t)
    if m: return {"intent": "save_work", "address": m.group(2).strip()}
    m = re.search(r"\bmi\s+casa\s+es[:\s]+(.+)$", t)
    if m: return {"intent": "save_home", "address": m.group(1).strip()}
    m = re.search(r"\bmi\s+trabajo\s+es[:\s]+(.+)$", t)
    if m: return {"intent": "save_work", "address": m.group(1).strip()}

    # =========== Borrar/olvidar ===========
    if re.search(r"\b(olvidar|borrar|eliminar)\s+casa\b", t):
        return {"intent": "delete_home"}
    if re.search(r"\b(olvidar|borrar|eliminar)\s+trabajo\b", t):
        return {"intent": "delete_work"}

    # =========== Toggles de preferencia ===========
    if re.search(r"\b(m[aá]s\s+r[aá]pida|prioriz[aá]?\s+r[aá]pido)\b", t):
        return {"intent": "faster"}
    if re.search(r"\b(menos\s+caminata|poco\s+caminar|evitar\s+caminar)\b", t):
        return {"intent": "less_walk"}
    if re.search(r"\b(sin\s+trasbordo[s]?|evitar\s+trasbordo[s]?)\b", t):
        return {"intent": "no_transfers"}

    # =========== Frecuencia / próximas ===========
    if re.search(r"\b(pr[oó]ximas|sale[n]?|pasa[n]?|cada cu[aá]nto|frecuen)\b", t):
        # admite "ver proximas", "cada cuanto pasa", etc.
        origin = None
        m = re.search(r"(cerca de|en)\s+(.+)$", t)  # "cerca de <lugar>" o "en <lugar>"
        if m:
            origin = m.group(2).strip()
        elif prefs.get("home_lat"):
            origin = "home"
        return {"intent": "next_arrivals", "origin": origin}

    # =========== Normalizar sinónimos para slots ===========
    # Mapeamos "casa", "mi casa" → home ; "trabajo", "laburo", "oficina", "mi trabajo" → work
    norm_for_slots = (
        " " + t + " "
    )
    norm_for_slots = (
        norm_for_slots
        .replace(" mi casa ", " home ")
        .replace(" casa ", " home ")
        .replace(" mi trabajo ", " work ")
        .replace(" trabajo ", " work ")
        .replace(" laburo ", " work ")
        .replace(" oficina ", " work ")
    ).strip()

    # =========== "usar casa a trabajo" / variantes ===========
    if re.search(r"\busar\s+home\s+a\s+work\b", norm_for_slots) or re.search(r"\bde\s+home\s+a\s+work\b", norm_for_slots):
        return {"intent": "route", "origin": "home", "dest": "work"}
    if re.search(r"\busar\s+work\s+a\s+home\b", norm_for_slots) or re.search(r"\bde\s+work\s+a\s+home\b", norm_for_slots):
        return {"intent": "route", "origin": "work", "dest": "home"}

    # =========== “ir de X a Y” / “de X a Y” / “a Y (usa home si existe)” ===========
    m = re.search(r"\bir\s+de\s+(.+?)\s+a\s+(.+)$", norm_for_slots)
    if m:
        return {"intent": "route", "origin": m.group(1).strip(), "dest": m.group(2).strip()}
    m = re.search(r"\bde\s+(.+?)\s+a\s+(.+)$", norm_for_slots)
    if m:
        return {"intent": "route", "origin": m.group(1).strip(), "dest": m.group(2).strip()}
    m = re.search(r"\ba\s+(.+)$", norm_for_slots)
    if m and prefs.get("home_lat"):
        return {"intent": "route", "origin": "home", "dest": m.group(1).strip()}

    # Nada claro
    return {"intent": "unknown"}

# --- Intento LLM opcional (si hay OPENAI_API_KEY). Fallback a reglas. ---
def detect_intent(text: str, prefs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Devuelve: {intent: str, ...slots}
    intents posibles:
      route, save_home, save_work, delete_home, delete_work,
      next_arrivals, faster, less_walk, no_transfers,
      choose_option, show_saved, unknown
    """
    prefs = prefs or {}
    # 1) Reglas primero (rápido y suficiente para la gran mayoría)
    out = _rule_based(text, prefs)
    if out.get("intent") != "unknown":
        return out

    # 2) LLM (opcional) para jergas raras / edge cases
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("GPT_API_KEY") or os.getenv("OPENAI_KEY")
    if not api_key:
        return out  # sin LLM, nos quedamos con reglas

    try:
        # evita dependencias si no están instaladas
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        sys = (
            "Sos un parser de intenciones para un bot de transporte urbano (colectivos en Argentina). "
            "Detectá una de estas intenciones y devolvé JSON estricto sin texto extra: "
            "route, save_home, save_work, delete_home, delete_work, next_arrivals, faster, less_walk, no_transfers, choose_option, show_saved, unknown. "
            "Para 'route' devolvé slots: origin, dest (pueden ser 'home' o 'work'). "
            "Para 'save_home'/'save_work' devolvé slot 'address'. "
            "Para 'choose_option' devolvé slot 'choice' (entero 1..9). "
            "Para 'next_arrivals' podés incluir 'origin' si el usuario lo dijo (sino null). "
            "Aceptá jergas como: 'la primera', 'la más rápida', 'ver casa', 'usar casa a trabajo', 'cada cuanto pasa', etc."
        )
        user = f"Texto: {text}\nPreferencias: {{'has_home': {bool(prefs.get('home_lat'))}, 'has_work': {bool(prefs.get('work_lat'))}}}"

        rsp = client.chat.completions.create(
            model=os.getenv("GPT_MODEL","gpt-4o-mini"),
            messages=[
                {"role":"system","content":sys},
                {"role":"user","content":user}
            ],
            temperature=0,
            response_format={"type":"json_object"}
        )
        content = rsp.choices[0].message.content
        import json
        parsed = json.loads(content)
        if isinstance(parsed, dict) and parsed.get("intent"):
            return parsed
        return out
    except Exception:
        return out
