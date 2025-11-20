import time, json, httpx

payload = {"user_id": "bench", "text": "ir de Corrientes 900 CABA a Av. Rivadavia 9000 CABA"}

t0 = time.perf_counter()
with httpx.Client(timeout=60) as c:
    r = c.post("http://localhost:8000/api/chat", json=payload)
dt = (time.perf_counter() - t0) * 1000

print(f"HTTP {r.status_code} en {dt:.1f} ms")
print((r.json().get("text") or "")[:400], "...")
