import pandas as pd
import os

# Coba cari file parquet di beberapa kemungkinan lokasi folder
paths = [
    'forecast_next_7_days.parquet',
    'data/forecast_next_7_days.parquet',
    'app/data/forecast_next_7_days.parquet',
    'backend/data/forecast_next_7_days.parquet'
]

df = None
for p in paths:
    if os.path.exists(p):
        print(f"File ditemukan di: {p}")
        df = pd.read_parquet(p)
        break

if df is not None:
    print("\nDaftar Komoditas dan ID-nya:")
    print(df[['commodity_no', 'commodity']].drop_duplicates().to_string(index=False))
else:
    print("Error: File parquet tidak ditemukan di folder manapun. Coba cek letak foldernya.")