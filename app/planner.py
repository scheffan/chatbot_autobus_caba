# app/planner.py
import math
import os
import sqlite3
import time
import logging
from typing import List, Dict, Tuple, Optional

# =========================
# Logging de performance
# =========================
log = logging.getLogger("planner-perf")
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

PERF_LOG = os.getenv("PERF_LOG", "1") != "0"  # habilitado por defecto

class Timer:
    def __init__(self, label: str):
        self.label = label
        self.t0 = None
    def __enter__(self):
        self.t0 = time.perf_counter()
        return self
    def __exit__(self, *_):
        if PERF_LOG:
            dt = (time.perf_counter() - self.t0) * 1000
            log.info(f"[{self.label}] {dt:.1f} ms")

class Dummy:
    def __enter__(self): return self
    def __exit__(self, *_): return False

# =========================
# Utilidades geométricas
# =========================
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371e3
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1)*math.sin(p2) - math.sin(p1)*math.cos(p2)*math.cos(dl)
    b = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    return b

def angle_diff(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d

def stop_id_variants(stop_id: str) -> List[str]:
    if not stop_id:
        return [stop_id]
    parts = stop_id.split("-")
    tail = parts[-1]
    return [stop_id] if tail == stop_id else [stop_id, tail]

# =========================
# Planner
# =========================
class Planner:
    """
    Planificador con:
      - PRAGMA de lectura para SQLite.
      - Precarga de 'stops' en memoria + grid espacial.
      - Cache de coordenadas y cache de mids (origen,destino).
      - Misma interfaz pública y formato de resultados que tu versión actual.
    """
    def __init__(self, sqlite_path: str):
        self.db = sqlite_path
        self.conn = sqlite3.connect(self.db, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        # PRAGMA seguros para solo-lectura
        try:
            self.conn.execute("PRAGMA journal_mode=OFF;")
            self.conn.execute("PRAGMA synchronous=NORMAL;")
            self.conn.execute("PRAGMA temp_store=MEMORY;")
            self.conn.execute("PRAGMA cache_size=-20000;")      # ~20MB
            self.conn.execute("PRAGMA mmap_size=268435456;")    # 256MB
        except Exception:
            pass

        # parámetros tunables por env
        self.MAX_CANDIDATES = int(os.getenv("PL_MAX_CANDIDATES", "200"))
        self.NEIGHBOR_LIMIT = int(os.getenv("PL_NEIGHBOR_LIMIT", "6"))
        self.NEIGHBOR_RADIUS = int(os.getenv("PL_NEIGHBOR_RADIUS", "300"))
        self.CORRIDOR_BEAM = float(os.getenv("PL_CORRIDOR_BEAM", "50.0"))

        # caches
        self._stop_coords_cache: Dict[str, Tuple[float, float]] = {}
        self._mids_cache: Dict[Tuple[str, str], List[str]] = {}

        # precarga stops + grid
        self._load_stops_into_memory()

    # ---------- precarga y grid ----------
    def _load_stops_into_memory(self):
        with Timer("bootstrap:load-stops") if PERF_LOG else Dummy():
            cur = self.conn.cursor()
            cur.execute("SELECT stop_id, stop_name, stop_lat, stop_lon FROM stops")
            rows = cur.fetchall()

        self._stops: List[Dict] = []
        self._stops_by_id: Dict[str, Dict] = {}

        # constantes para grilla ~250m
        self._lat_deg_m = 111320.0
        # si no sabés la lat, asumí BA ~ -34
        self._lon_deg_m = 111320.0 * math.cos(math.radians(-34.6))
        self._cell_m = 250.0
        self._cell_lat = self._cell_m / self._lat_deg_m
        self._cell_lon = self._cell_m / self._lon_deg_m

        self._grid: Dict[Tuple[int, int], List[Dict]] = {}

        with Timer("bootstrap:index-grid") if PERF_LOG else Dummy():
            for r in rows:
                item = {
                    "stop_id": r["stop_id"],
                    "stop_name": r["stop_name"],
                    "stop_lat": float(r["stop_lat"]),
                    "stop_lon": float(r["stop_lon"]),
                }
                self._stops.append(item)
                self._stops_by_id[item["stop_id"]] = item
                key = self._grid_key(item["stop_lat"], item["stop_lon"])
                self._grid.setdefault(key, []).append(item)

    def _grid_key(self, lat: float, lon: float) -> Tuple[int, int]:
        ix = int(lat / self._cell_lat)
        iy = int(lon / self._cell_lon)
        return (ix, iy)

    def _grid_candidates(self, lat: float, lon: float, radius_m: int):
        """Devuelve candidatos por celdas adyacentes dentro del radio aprox."""
        if radius_m <= 0:
            return []
        rx = int(math.ceil((radius_m / self._cell_m)))
        ky = self._grid_key(lat, lon)
        out = []
        for dx in range(-rx, rx + 1):
            for dy in range(-rx, rx + 1):
                out.extend(self._grid.get((ky[0] + dx, ky[1] + dy), []))
        return out

    # ---------- STOPS ----------
    def nearest_stops(
        self,
        lat: float,
        lon: float,
        limit: int = 6,
        start_radius_m: int = 120,
        step_m: int = 120,
        max_radius_m: int = 1000,
    ) -> List[Dict]:
        out = []
        seen = set()
        radius = max(1, start_radius_m)

        with Timer("nearest_stops:expand-grid") if PERF_LOG else Dummy():
            while radius <= max_radius_m and len(out) < limit:
                cands = self._grid_candidates(lat, lon, radius)
                if not cands:
                    radius += step_m
                    continue
                batch = []
                for r in cands:
                    sid = r["stop_id"]
                    if sid in seen:
                        continue
                    d = haversine(r["stop_lat"], r["stop_lon"], lat, lon)
                    if d <= radius:
                        seen.add(sid)
                        batch.append((d, r))
                if batch:
                    batch.sort(key=lambda x: x[0])
                    for dist, row in batch:
                        out.append({
                            "stop_id": row["stop_id"],
                            "stop_name": row["stop_name"],
                            "stop_lat": row["stop_lat"],
                            "stop_lon": row["stop_lon"],
                            "distance_m": dist
                        })
                        if len(out) >= limit:
                            break
                radius += step_m

        if len(out) < limit:
            # fallback: ordenar todos los de la grilla próxima
            with Timer("nearest_stops:fallback-grid-sort") if PERF_LOG else Dummy():
                scored = []
                cands = self._grid_candidates(lat, lon, max_radius_m)
                if not cands:
                    cands = self._stops  # último recurso
                for r in cands:
                    sid = r["stop_id"]
                    if sid in seen:
                        continue
                    d = haversine(r["stop_lat"], r["stop_lon"], lat, lon)
                    scored.append((d, r))
                scored.sort(key=lambda x: x[0])
                for dist, row in scored:
                    out.append({
                        "stop_id": row["stop_id"],
                        "stop_name": row["stop_name"],
                        "stop_lat": row["stop_lat"],
                        "stop_lon": row["stop_lon"],
                        "distance_m": dist
                    })
                    if len(out) >= limit:
                        break

        out.sort(key=lambda x: x["distance_m"])
        return out[:limit]

    def stop_coords(self, stop_id: str) -> Optional[Tuple[float, float]]:
        # cache
        if stop_id in self._stop_coords_cache:
            return self._stop_coords_cache[stop_id]
        # memoria
        obj = self._stops_by_id.get(stop_id)
        if obj:
            val = (obj["stop_lat"], obj["stop_lon"])
            self._stop_coords_cache[stop_id] = val
            return val
        # tolerante (sin prefijo)
        ids = stop_id_variants(stop_id)
        ph = ",".join(["?"] * len(ids))
        cur = self.conn.cursor()
        with Timer("stop_coords:lookup") if PERF_LOG else Dummy():
            cur.execute(f"SELECT stop_lat, stop_lon FROM stops WHERE stop_id IN ({ph}) LIMIT 1", ids)
            r = cur.fetchone()
        if not r:
            return None
        val = (float(r[0]), float(r[1]))
        self._stop_coords_cache[stop_id] = val
        return val

    def nearby_stops(self, lat: float, lon: float, radius_m: int = 250, limit: int = 12) -> List[Dict]:
        with Timer("nearby_stops:grid-cands") if PERF_LOG else Dummy():
            cands = self._grid_candidates(lat, lon, radius_m)
            if not cands:
                cands = self._stops
        out = []
        with Timer("nearby_stops:filter") if PERF_LOG else Dummy():
            for r in cands:
                d = haversine(r["stop_lat"], r["stop_lon"], lat, lon)
                if d <= radius_m:
                    out.append({
                        "stop_id": r["stop_id"],
                        "stop_name": r["stop_name"],
                        "distance_m": d
                    })
        out.sort(key=lambda x: x["distance_m"])
        return out[:limit]

    # ---------- TIEMPOS ----------
    def next_departures(self, stop_id: str, limit: int = 3) -> List[Dict]:
        cur = self.conn.cursor()
        cur.execute("SELECT (strftime('%H','now','localtime')*3600 + strftime('%M','now','localtime')*60 + strftime('%S','now','localtime'))")
        now_s = int(cur.fetchone()[0])

        ids = stop_id_variants(stop_id)
        ph = ",".join(["?"] * len(ids))
        q = f"""
            SELECT st.departure_time, r.route_short_name
            FROM stop_times st
            JOIN trips t ON t.trip_id = st.trip_id
            LEFT JOIN routes r ON r.route_id = t.route_id
            WHERE st.stop_id IN ({ph}) AND CAST(st.departure_time AS INTEGER) >= ?
            ORDER BY st.departure_time
            LIMIT ?
        """
        with Timer("next_departures:query") if PERF_LOG else Dummy():
            cur.execute(q, (*ids, now_s, limit))
            rows = cur.fetchall()
        out = []
        for r in rows:
            dep = int(r["departure_time"])
            hm = f"{dep//3600:02d}:{(dep%3600)//60:02d}"
            out.append({"hm": hm, "route_short_name": r["route_short_name"]})
        return out

    def headway_estimate(self, stop_id: str, window_minutes: int = 60) -> Optional[Tuple[int, int]]:
        cur = self.conn.cursor()
        cur.execute("SELECT (strftime('%H','now','localtime')*3600 + strftime('%M','now','localtime')*60 + strftime('%S','now','localtime'))")
        now_s = int(cur.fetchone()[0])
        lo, hi = now_s - window_minutes*60, now_s + window_minutes*60

        ids = stop_id_variants(stop_id)
        ph = ",".join(["?"] * len(ids))
        q = f"""
            SELECT CAST(st.departure_time AS INTEGER) dep
            FROM stop_times st
            WHERE st.stop_id IN ({ph}) AND CAST(st.departure_time AS INTEGER) BETWEEN ? AND ?
            ORDER BY dep
        """
        with Timer("headway:query") if PERF_LOG else Dummy():
            cur.execute(q, (*ids, lo, hi))
            ts = [int(r["dep"]) for r in cur.fetchall()]
        if len(ts) < 3:
            return None
        diffs = [ts[i+1]-ts[i] for i in range(len(ts)-1)]
        diffs.sort()
        k = max(1, len(diffs)//5)
        core = diffs[k:-k] if len(diffs) > 2*k else diffs
        if not core:
            core = diffs
        return (int(min(core)/60), int(max(core)/60))

    # ---------- RUTAS ----------
    def _route_short_for_trip(self, trip_id: str) -> str:
        cur = self.conn.cursor()
        cur.execute("""
            SELECT r.route_short_name
            FROM trips t JOIN routes r ON t.route_id=r.route_id
            WHERE t.trip_id=? LIMIT 1
        """, (trip_id,))
        r = cur.fetchone()
        return r[0] if r else ""

    def _headsign_for_trip(self, trip_id: str) -> str:
        cur = self.conn.cursor()
        cur.execute("SELECT trip_headsign FROM trips WHERE trip_id=? LIMIT 1", (trip_id,))
        r = cur.fetchone()
        return r[0] if r else ""

    def direct_routes(self, stop_o: str, stop_d: str, limit: int = 3) -> List[Dict]:
        cur = self.conn.cursor()
        ids_o, ids_d = stop_id_variants(stop_o), stop_id_variants(stop_d)
        ph_o, ph_d = ",".join(["?"]*len(ids_o)), ",".join(["?"]*len(ids_d))
        q = f"""
            SELECT DISTINCT so.trip_id, r.route_short_name, r.route_long_name,
                   CAST(so.departure_time AS INTEGER) dep,
                   CAST(sd.arrival_time   AS INTEGER) arr,
                   so.stop_id so_id, sd.stop_id sd_id, t.trip_headsign
            FROM stop_times so
            JOIN stop_times sd ON sd.trip_id=so.trip_id
                               AND CAST(sd.stop_sequence AS INTEGER) > CAST(so.stop_sequence AS INTEGER)
            JOIN trips t ON t.trip_id=so.trip_id
            LEFT JOIN routes r ON r.route_id=t.route_id
            WHERE so.stop_id IN ({ph_o}) AND sd.stop_id IN ({ph_d})
            ORDER BY (arr - dep) ASC
            LIMIT ?
        """
        with Timer("direct:query") if PERF_LOG else Dummy():
            cur.execute(q, (*ids_o, *ids_d, limit))
            rows = cur.fetchall()
        out = []
        for r in rows:
            dep, arr = int(r["dep"]), int(r["arr"])
            dur = max(1, round((arr - dep)/60))
            out.append({
                "type": "direct",
                "trip_id": r["trip_id"],
                "route_short": r["route_short_name"] or "",
                "route_long": r["route_long_name"] or "",
                "headsign": r["trip_headsign"] or "",
                "orig_stop_id": r["so_id"],
                "dest_stop_id": r["sd_id"],
                "duration_min": int(dur)
            })
        return out

    # --------- CORREDOR / SONAR ---------
    def _corridor_mids(self, origin_stop: str, dest_stop: str) -> List[str]:
        # cache (origen,destino)
        key = (origin_stop, dest_stop)
        if key in self._mids_cache:
            return self._mids_cache[key][:]

        cur = self.conn.cursor()
        ids_o = stop_id_variants(origin_stop)
        ph_o = ",".join(["?"]*len(ids_o))

        co = self.stop_coords(origin_stop)
        cd = self.stop_coords(dest_stop)

        with Timer("corridor:raw-mids") if PERF_LOG else Dummy():
            cur.execute(f"""
                SELECT DISTINCT s2.stop_id mid
                FROM stop_times s1
                JOIN stop_times s2 ON s2.trip_id=s1.trip_id
                WHERE s1.stop_id IN ({ph_o})
                  AND CAST(s2.stop_sequence AS INTEGER) > CAST(s1.stop_sequence AS INTEGER)
                LIMIT ?
            """, (*ids_o, self.MAX_CANDIDATES))
            mids_raw = [r["mid"] for r in cur.fetchall()]

        if not co or not cd:
            self._mids_cache[key] = mids_raw
            return mids_raw[:]

        boref = bearing(co[0], co[1], cd[0], cd[1])
        d_od  = haversine(co[0], co[1], cd[0], cd[1])

        mids: List[str] = []
        with Timer("corridor:filter-geometry") if PERF_LOG else Dummy():
            for mid in mids_raw:
                mc = self.stop_coords(mid)
                if not mc:
                    continue
                b = bearing(co[0], co[1], mc[0], mc[1])
                if angle_diff(boref, b) > self.CORRIDOR_BEAM:
                    continue
                if haversine(mc[0], mc[1], cd[0], cd[1]) > d_od * 1.3:
                    continue
                mids.append(mid)

        self._mids_cache[key] = mids
        return mids[:]

    # ---------- 1 (y 2) TRASBORDOS ----------
    def one_transfer(
        self,
        stop_o: str,
        stop_d: str,
        max_wait_min: int = 20,
        walk_radius_m: int = None,
        limit: int = 6,
        allow_two_transfers: bool = False,
    ) -> List[Dict]:
        if walk_radius_m is None:
            walk_radius_m = self.NEIGHBOR_RADIUS

        cur = self.conn.cursor()
        results: List[Dict] = []

        orig_set = [stop_o]
        dest_set = [stop_d]

        with Timer("one_transfer:build-orig-dest-sets") if PERF_LOG else Dummy():
            co = self.stop_coords(stop_o)
            cd = self.stop_coords(stop_d)
            if co:
                for nb in self.nearby_stops(co[0], co[1], radius_m=250, limit=8):
                    if nb["stop_id"] not in orig_set:
                        orig_set.append(nb["stop_id"])
            if cd:
                for nb in self.nearby_stops(cd[0], cd[1], radius_m=250, limit=8):
                    if nb["stop_id"] not in dest_set:
                        dest_set.append(nb["stop_id"])

        boref = bearing(co[0], co[1], cd[0], cd[1]) if (co and cd) else None
        d_od  = haversine(co[0], co[1], cd[0], cd[1]) if (co and cd) else None

        def mid_penalty(mid_id: str) -> float:
            if not co or not cd:
                return 0.0
            mc = self.stop_coords(mid_id)
            if not mc:
                return 0.0
            pen = 0.0
            d_md = haversine(mc[0], mc[1], cd[0], cd[1])
            if d_od is not None and d_md > d_od * 1.15:
                pen += 10.0
            if boref is not None:
                b = bearing(co[0], co[1], mc[0], mc[1])
                ad = angle_diff(boref, b)
                if ad > 45:
                    pen += (ad - 45) / 5.0
            return pen

        mids_cache = {}
        with Timer("one_transfer:pre-corridor") if PERF_LOG else Dummy():
            for o_id in orig_set:
                mids = self._corridor_mids(o_id, stop_d)
                mids.sort(key=lambda m: mid_penalty(m))
                mids_cache[o_id] = mids

        # 1-TRANSFER
        for o_id in orig_set:
            ids_o = stop_id_variants(o_id)
            for mid in mids_cache.get(o_id, [])[:300]:
                ids_mid = stop_id_variants(mid)

                with Timer("one_transfer:leg1-o->mid") if PERF_LOG else Dummy():
                    cur.execute(f"""
                        SELECT s1.trip_id, CAST(s1.departure_time AS INTEGER) dep,
                               CAST(s2.arrival_time   AS INTEGER) arr
                        FROM stop_times s1
                        JOIN stop_times s2 ON s2.trip_id=s1.trip_id
                        WHERE s1.stop_id IN ({",".join(["?"]*len(ids_o))})
                          AND s2.stop_id IN ({",".join(["?"]*len(ids_mid))})
                          AND CAST(s2.stop_sequence AS INTEGER) > CAST(s1.stop_sequence AS INTEGER)
                        ORDER BY (CAST(s2.arrival_time AS INTEGER) - CAST(s1.departure_time AS INTEGER)) ASC
                        LIMIT 1
                    """, (*ids_o, *ids_mid))
                    leg1 = cur.fetchone()
                if not leg1:
                    continue
                arr_mid = int(leg1["arr"])

                mc = self.stop_coords(mid)
                if not mc:
                    continue

                with Timer("one_transfer:neighbors-around-mid") if PERF_LOG else Dummy():
                    neighbors = [{"stop_id": mid, "distance_m": 0.0}] + self.nearby_stops(mc[0], mc[1], radius_m=walk_radius_m, limit=self.NEIGHBOR_LIMIT)

                for nb in neighbors:
                    nb_id = nb["stop_id"]
                    ids_nb = stop_id_variants(nb_id)
                    for d_id in dest_set:
                        ids_d = stop_id_variants(d_id)

                        with Timer("one_transfer:leg2-mid->dest") if PERF_LOG else Dummy():
                            cur.execute(f"""
                                SELECT sm.trip_id, CAST(sm.departure_time AS INTEGER) dep2,
                                       CAST(sd.arrival_time   AS INTEGER) arr2
                                FROM stop_times sm
                                JOIN stop_times sd ON sd.trip_id=sm.trip_id
                                WHERE sm.stop_id IN ({",".join(["?"]*len(ids_nb))})
                                  AND sd.stop_id IN ({",".join(["?"]*len(ids_d))})
                                  AND CAST(sd.stop_sequence AS INTEGER) > CAST(sm.stop_sequence AS INTEGER)
                                  AND CAST(sm.departure_time AS INTEGER) BETWEEN ? AND ?
                                ORDER BY (CAST(sd.arrival_time AS INTEGER) - CAST(sm.departure_time AS INTEGER)) ASC
                                LIMIT 1
                            """, (*ids_nb, *ids_d, arr_mid, arr_mid + max_wait_min*60))
                            leg2 = cur.fetchone()
                        if not leg2:
                            continue

                        r1 = self._route_short_for_trip(leg1["trip_id"])
                        r2 = self._route_short_for_trip(leg2["trip_id"])
                        h1 = self._headsign_for_trip(leg1["trip_id"])
                        h2 = self._headsign_for_trip(leg2["trip_id"])

                        wait = int(leg2["dep2"]) - int(leg1["arr"])
                        walk_s = int(nb["distance_m"] / 1.2)
                        total_s = ((int(leg1["arr"]) - int(leg1["dep"])) +
                                   (int(leg2["arr2"]) - int(leg2["dep2"])) +
                                   max(0, wait) + walk_s + 30)
                        dur_min = max(1, round(total_s/60))
                        dur_min = int(dur_min + mid_penalty(mid))

                        results.append({
                            "type": "transfer",
                            "legs": [
                                {"from_stop": o_id,  "to_stop": mid,  "trip_id": leg1["trip_id"], "route_short": r1, "headsign": h1},
                                {"from_stop": nb_id, "to_stop": d_id, "trip_id": leg2["trip_id"], "route_short": r2, "headsign": h2},
                            ],
                            "mid_stop": mid,
                            "walk_m": int(nb["distance_m"]),
                            "wait_s": int(wait),
                            "duration_min": int(dur_min),
                        })
                        if len(results) >= limit:
                            return results

        if not results and allow_two_transfers:
            return []

        return results
