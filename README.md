# 🚌 Colectivos Demo Plus – Planificador + Chatbot

Proyecto demo de planificador de colectivos para la Ciudad de Buenos Aires, construido sobre:

- Backend **FastAPI**
- Datos oficiales **GTFS** de colectivos CABA
- Chat estilo asistente (web y Telegram)
- Síntesis de voz (TTS) local en Windows

El objetivo es tener un ejemplo completo de **chatbot de transporte** que use datos reales.

---

## 🚀 Funcionalidades

- Búsqueda de rutas entre dos direcciones (ej: "ir de Corrientes 900 a Plaza de Mayo").
- Consulta de **próximas salidas** y horarios.
- Manejo de preferencias de usuario (modo rápido / balanceado, favoritos hogar/trabajo, etc.).
- Interfaz web de chat.
- Bot de Telegram (opcional).
- TTS local (opcional, solo Windows).

Los datos de colectivos provienen de:

- Dataset oficial **“colectivos-gtfs”** del Gobierno de la Ciudad de Buenos Aires.
- Versión **simplificada por frecuencias** publicada en el TUMI Datahub.

---

## 📂 Estructura del proyecto (resumen)

```text
colectivos_demo_plus/
├── app/
│   ├── main.py
│   ├── planner.py
│   ├── intents.py
│   ├── geocode.py
│   ├── storage.py
│   └── ...
├── web/
│   └── index.html
├── tools/
│   └── gtfs_load.py
├── data/
│   ├── .gitkeep
│   └── (GTFS aquí)
├── telegram_bot.py
├── requirements.txt
├── .env.example
└── README.md
```

---

## ✅ Requisitos

- **Windows 10/11** (recomendado)
- **Python 3.10+**
- Dependencias del proyecto via `requirements.txt`

---

## 1️⃣ Clonar el repositorio

```powershell
git clone https://github.com/TU_USUARIO/colectivos_demo_plus.git
cd colectivos_demo_plus
```

---

## 2️⃣ Crear y activar el entorno virtual

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

---

## 3️⃣ Instalar dependencias

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 4️⃣ Configurar `.env`

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=clave
OPENAI_API_KEY=
CITY_NAME=CABA
MODE=balanced

GTFS_SQLITE=data/gtfs.sqlite
APPDATA_SQLITE=data/appdata.sqlite

TTS_ENABLED=1
TTS_VOICE=es-ES
TTS_DIR=data/tts
TTS_RATE=0
TTS_VOLUME=1
```

Copiar plantilla:

```powershell
copy .env.example .env
```

---

## 5️⃣ Descargar datos GTFS oficiales

### Fuente 1: Colectivos CABA  
https://data.buenosaires.gob.ar/fi/dataset/colectivos-gtfs

### Fuente 2: Dataset por frecuencias (opcional)  
https://hub.tumidata.org/dataset/buses_gtfs_frequency_buenos_aires

Extraer todos los `.txt` en:

```
data/gtfs/
```

---

## 6️⃣ Generar `gtfs.sqlite` (~4 GB)

```powershell
python tools/gtfs_load.py --gtfs_dir data/gtfs --sqlite data/gtfs.sqlite
```

---

## 7️⃣ Ejecutar el backend

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Abrir:
http://localhost:8000

---

## 8️⃣ Ejecutar el bot de Telegram (opcional)

```powershell
python telegram_bot.py
```

---

## 🧪 Pruebas rápidas

```powershell
python bench_request.py
```

---

## 📄 Licencia

Distribuido bajo la licencia MIT.
