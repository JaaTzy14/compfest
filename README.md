# ProcureAI

ProcureAI adalah aplikasi rekomendasi procurement bahan pangan. Frontend memakai Next.js, sedangkan backend memakai FastAPI untuk optimasi rencana belanja berdasarkan forecast harga, lokasi pengguna, deadline, dan preferensi risiko.

## Struktur Project

```text
.
├── backend/   # FastAPI, optimizer, refresh data, model forecast
└── frontend/  # Next.js UI
```

## Prasyarat

Untuk setup manual:

- Node.js 20+
- npm
- Python 3.11+
- pip

Untuk setup Docker:

- Docker
- Docker Compose

## Setup Dengan Docker Compose

Jalankan semua service dari root project:

```bash
docker compose up --build
```

Setelah container aktif:

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- Dokumentasi API: http://localhost:8000/docs

Untuk menghentikan service:

```bash
docker compose down
```

Untuk rebuild setelah perubahan dependency:

```bash
docker compose build --no-cache
docker compose up
```

## Setup Manual

### 1. Jalankan Backend

Masuk ke folder backend:

```bash
cd backend
```

Buat virtual environment:

```bash
python -m venv .venv
```

Aktifkan virtual environment.

Windows PowerShell:

```bash
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependency:

```bash
pip install -r requirements.txt
```

Jalankan FastAPI:

```bash
fastapi dev app/main.py --reload-dir app
```

Backend akan berjalan di http://localhost:8000.

### 2. Jalankan Frontend

Buka terminal baru, lalu masuk ke folder frontend:

```bash
cd frontend
```

Install dependency:

```bash
npm install
```

Jalankan development server:

```bash
npm run dev
```

Frontend akan berjalan di http://localhost:3000.

## Endpoint Utama

### Optimasi Procurement

```http
POST /api/v1/optimize
```

Contoh payload:

```json
{
  "location": [-6.2, 106.8],
  "commodities": {
    "8": 10,
    "12": 5
  },
  "deadline": "2026-08-28",
  "max_markets": 2,
  "max_trips": 2,
  "risk_aversion": 0.5,
  "allow_split": false
}
```

### Refresh Data

```http
POST /api/v1/refresh
```

Contoh payload optional:

```json
{
  "year_month": "2026-08"
}
```

Jika `year_month` tidak dikirim, backend memakai bulan berjalan berdasarkan timezone Asia/Jakarta.

## Catatan Data dan Model

Backend membutuhkan file berikut agar endpoint optimasi berjalan:

- `backend/data/prices_split_base.parquet`
- `backend/data/forecast_next_7_days.parquet`
- `backend/app/forecasting/models/*`
- `backend/app/forecasting/config/*`

File tersebut sudah berada di repository ini, sehingga setup Docker Compose maupun manual bisa langsung menjalankan aplikasi tanpa langkah download model tambahan.

## Troubleshooting

Jika frontend tidak bisa menghubungi backend, pastikan backend berjalan di port `8000` karena frontend melakukan request ke `http://localhost:8000`.

Jika port `3000` atau `8000` sudah dipakai, hentikan proses lain yang memakai port tersebut atau ubah mapping port di `docker-compose.yml`.

Jika refresh data gagal, cek koneksi internet karena endpoint refresh mengambil data dari API Info Pangan Jakarta.
