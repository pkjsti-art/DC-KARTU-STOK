import pandas as pd
import numpy as np

def process_data(file):
    # Membaca file Excel mentah
    df_raw = pd.read_excel(file, header=None)
    
    # 1. Cleaning Data & Deteksi Header Dinamis
    header_idx = -1
    for idx, row in df_raw.iterrows():
        # Modifikasi: menggunakan list comprehension untuk mencegah error float/NaN
        row_str = " ".join([str(val).lower() for val in row])
        if 'tanggal' in row_str and 'qty' in row_str:
            header_idx = idx
            break
            
    if header_idx == -1:
        raise ValueError("Header tabel (Tanggal, Qty) tidak ditemukan. Pastikan format file benar.")

    # Menjadikan baris yang terdeteksi sebagai header dan membuang baris di atasnya
    df = pd.read_excel(file, header=header_idx)
    
    # Membuang baris Saldo Awal jika ada
    df = df[~df.astype(str).apply(lambda x: x.str.contains('Saldo Awal', case=False, na=False)).any(axis=1)].copy()
    df = df.dropna(how='all').reset_index(drop=True)
    
    # Memastikan format kolom numerik
    for col in ['Qty', 'Trx Qty', 'Saldo']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
    # Mengamankan format Tanggal
    if 'Tanggal' in df.columns:
        df['Tanggal_Parsed'] = pd.to_datetime(df['Tanggal'], errors='coerce')
    
    # 2. Preparation Data
    df['Status'] = ""
    df['Kode_Trx'] = df['Keterangan'].str.extract(r'((?:MOV|MB)/[A-Za-z0-9/]+)')
    
    # Flagging jenis transaksi
    ket_lower = df['Keterangan'].str.lower().fillna("")
    df['Is_MOV_In'] = ket_lower.str.contains('mov') & ket_lower.str.contains('penambahan')
    df['Is_MB_Out'] = ket_lower.str.contains('mb') & ket_lower.str.contains('pengeluaran')
    df['Is_MOV_Out'] = ket_lower.str.contains('mov') & ket_lower.str.contains('pengurangan')
    df['Is_Target_Out'] = df['Is_MB_Out'] | df['Is_MOV_Out']

    # 3. Crosscheck Data
    # Mengelompokkan berdasarkan nilai Qty yang unik
    unique_qtys = df[df['Is_MOV_In'] | df['Is_Target_Out']]['Qty'].dropna().unique()
    
    for qty in unique_qtys:
        # Index dari transaksi penambahan dan pengeluaran dengan Qty yang sama
        idx_in = df[(df['Is_MOV_In']) & (df['Qty'] == qty)].index.tolist()
        idx_out = df[(df['Is_Target_Out']) & (df['Qty'] == qty)].index.tolist()
        
        # Skenario: Qty match tidak ada sama sekali
        if not idx_out:
            df.loc[idx_in, 'Status'] = "MOV Belum MB / Not Match"
            continue
        if not idx_in:
            for idx in idx_out:
                if df.loc[idx, 'Is_MB_Out']:
                    df.loc[idx, 'Status'] = "MB belum di PG / Not Match"
                else:
                    df.loc[idx, 'Status'] = "MOV Pengurangan Not Match"
            continue
            
        # Mengurutkan target out berdasarkan tanggal
        idx_out.sort(key=lambda x: df.loc[x, 'Tanggal_Parsed'] if pd.notnull(df.loc[x, 'Tanggal_Parsed']) else pd.Timestamp.min)
        
        # Pencocokan 1:1
        for i_in in idx_in:
            if not idx_out:
                # Target out sudah habis terpasangkan, sisa MOV in terindikasi duplikat
                df.loc[i_in, 'Status'] = "Indikasi Pindah Gudang Duplikat / Belum MB"
            else:
                date_in = df.loc[i_in, 'Tanggal_Parsed']
                
                # Mencari index di idx_out dengan tanggal terdekat
                best_match_idx = 0
                if pd.notnull(date_in):
                    min_diff = pd.Timedelta(days=100000)
                    for j, i_out in enumerate(idx_out):
                        date_out = df.loc[i_out, 'Tanggal_Parsed']
                        if pd.notnull(date_out):
                            diff = abs(date_in - date_out)
                            if diff < min_diff:
                                min_diff = diff
                                best_match_idx = j
                
                # Ambil dan hapus dari list (agar 1:1)
                matched_out = idx_out.pop(best_match_idx)
                
                # Tulis output status
                kode_in = df.loc[i_in, 'Kode_Trx']
                kode_out = df.loc[matched_out, 'Kode_Trx']
                df.loc[i_in, 'Status'] = f"Match dgn {kode_out if pd.notna(kode_out) else 'Unknown'}"
                df.loc[matched_out, 'Status'] = f"Match dgn {kode_in if pd.notna(kode_in) else 'Unknown'}"
                
        # Jika ada sisa idx_out yang tidak mendapat pasangan
        for idx in idx_out:
            if df.loc[idx, 'Is_MB_Out']:
                df.loc[idx, 'Status'] = "MB belum di PG / Not Match"
            else:
                df.loc[idx, 'Status'] = "MOV Pengurangan Not Match"

    # 4. Finalisasi Output
    kolom_drop = ['Tanggal_Parsed', 'Kode_Trx', 'Is_MOV_In', 'Is_MB_Out', 'Is_MOV_Out', 'Is_Target_Out']
    df = df.drop(columns=[col for col in kolom_drop if col in df.columns])
    
    return df
