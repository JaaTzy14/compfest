from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.optimize import router as optimize_router
from app.api.refresh import router as refresh_router

app = FastAPI()

# 1. Pasang CORS di sini (hanya sekali)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Mengizinkan akses dari semua frontend (termasuk localhost:3000)
    allow_credentials=True,
    allow_methods=["*"],  # Mengizinkan semua method (GET, POST, OPTIONS, dll)
    allow_headers=["*"],
)

# 2. Masukkan router optimize buatan teman Anda
app.include_router(optimize_router)
app.include_router(refresh_router)
