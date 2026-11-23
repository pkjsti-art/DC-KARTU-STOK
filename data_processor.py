import pandas as pd
import numpy as np
from collections import Counter


def deteksi_jenis_transaksi(keterangan):
    """Mengklasifikasikan jenis baris transaksi berdasarkan kolom Keterangan."""
    teks = str(keterangan).lower() if pd.notna(keterangan) else ""
    if "mov" in teks and "penambahan" in teks:
        return "MOV_IN"
    elif "mb" in teks and "pengeluaran" in teks:
        return "MB_OUT"
    elif "mov" in teks and "pengurangan" in teks:
        return "MOV_OUT"
    return "LAINNYA"


def deteksi_kategori_status(status):
    """Mengklasifikasikan kategori warna untuk kolom Status."""
    teks = str(status) if pd.notna(status) else ""
    if not teks.strip():
        return "KOSONG"
    if teks.startswith("Match Rekap") or teks.startswith("Match Parsial"):
        return "MATCH_REKAP"
    if teks.startswith("Match dgn"):
        return "MATCH_1_1"
    if teks.startswith("Indikasi Duplikat"):
        return "DUPLIKAT"
    return "NOT_MATCH"


def _format_daftar_kode(daftar_kode):
    """Merapikan daftar kode pasangan agar kode yang berulang ditampilkan ringkas (misal: MB/.../0095 (x3))."""
    kode_bersih = [k if pd.notna(k) and str(k).strip() else "Unknown" for k in daftar_kode]
    hitungan = Counter(kode_bersih)
    hasil = []
    sudah_masuk = set()
    for kode in kode_bersih:
        if kode not in sudah_masuk:
            sudah_masuk.add(kode)
            if hitungan[kode] > 1:
                hasil.append(f"{kode} (x{hitungan[kode]})")
            else:
                hasil.append(kode)
    return ", ".join(hasil)


def _hitung_selisih_hari(tgl_a, tgl_b):
    """Menghitung selisih hari absolut antara dua tanggal. Mengembalikan nilai besar jika tanggal kosong."""
    if pd.notnull(tgl_a) and pd.notnull(tgl_b):
        return abs((tgl_a - tgl_b).days)
    return 999999


def _cari_kombinasi_rekap(target_qty, daftar_kandidat, max_pecahan=8, max_langkah=5000):
    """
    Mencari kombinasi kandidat (minimal 2 transaksi) yang total Qty-nya sama persis dengan target_qty.
    Prioritas:
    1. Jumlah pecahan paling sedikit terlebih dahulu (2, 3, ..., max_pecahan).
    2. Tanggal paling dekat (daftar_kandidat sudah diurutkan berdasarkan selisih hari terkecil).
    Dilengkapi pruning dan batas langkah (max_langkah) agar cepat dan tidak hang.
    """
    n = len(daftar_kandidat)
    if n < 2:
        return None

    qtys = [item[1] for item in daftar_kandidat]
    total_semua = sum(qtys)
    if total_semua < target_qty:
        return None

    # Cek cepat: apakah seluruh kandidat jika ditotal langsung klop dengan target
    if total_semua == target_qty and n <= max_pecahan:
        return [item[0] for item in daftar_kandidat]

    # Precompute batas atas & bawah (suffix) untuk memangkas cabang hitungan yang mustahil
    suffix_sum = [0] * (n + 1)
    max_after = [0] * n
    min_after = [0] * n
    running_sum = 0
    running_max = -1
    running_min = float("inf")
    for i in range(n - 1, -1, -1):
        val = qtys[i]
        running_sum += val
        suffix_sum[i] = running_sum
        if val > running_max:
            running_max = val
        if val < running_min:
            running_min = val
        max_after[i] = running_max
        min_after[i] = running_min

    langkah = [0]
    batas_ukuran = min(max_pecahan, n)

    def dfs(start_idx, sisa_slot, sisa_target, pilihan_posisi):
        langkah[0] += 1
        if langkah[0] > max_langkah:
            return None

        if sisa_slot == 0:
            return pilihan_posisi if sisa_target == 0 else None

        if start_idx + sisa_slot > n or sisa_target <= 0:
            return None

        # Pruning: hentikan jika target di luar jangkauan matematis kandidat tersisa
        if sisa_target > suffix_sum[start_idx]:
            return None
        if sisa_target > sisa_slot * max_after[start_idx]:
            return None
        if sisa_target < sisa_slot * min_after[start_idx]:
            return None

        # Optimasi slot terakhir: langsung cari nilai sisa_target tanpa rekursi tambahan
        if sisa_slot == 1:
            for i in range(start_idx, n):
                if qtys[i] == sisa_target:
                    return pilihan_posisi + [i]
            return None

        qty_sudah_dicoba = set()
        for i in range(start_idx, n - sisa_slot + 1):
            if langkah[0] > max_langkah:
                return None

            nilai = qtys[i]
            if nilai >= sisa_target or nilai in qty_sudah_dicoba:
                continue
            qty_sudah_dicoba.add(nilai)

            hasil = dfs(i + 1, sisa_slot - 1, sisa_target - nilai, pilihan_posisi + [i])
            if hasil is not None:
                return hasil

        return None

    # Pencarian bertahap dari kombinasi pecahan terkecil (2 transaksi, lalu 3, dst.)
    for ukuran in range(2, batas_ukuran + 1):
        if langkah[0] > max_langkah:
            break
        posisi_cocok = dfs(0, ukuran, target_qty, [])
        if posisi_cocok is not None:
            return [daftar_kandidat[pos][0] for pos in posisi_cocok]

    return None


def _bangun_lapisan_tanggal(max_selisih_hari):
    """Menyusun urutan lapisan selisih hari dari terdekat ke terjauh (Progressive Date Rings)."""
    lapisan_standar = [0, 3, 7, 14, 30]
    if max_selisih_hari is None:
        return lapisan_standar + [None]

    lapisan = [hari for hari in lapisan_standar if hari < max_selisih_hari]
    lapisan.append(max_selisih_hari)
    return lapisan


def process_data(file, aktifkan_rekap=True, max_selisih_hari=None, max_pecahan=8):
    """
    Memproses data kartu stok:
    1. Cleaning & Deteksi Header Dinamis
    2. Preparation & Klasifikasi Transaksi
    3. Tahap 1: Match 1 vs 1 (prioritas selisih tanggal terdekat)
    4. Tahap 2: Match Rekap 1-to-Many & Many-to-1 (Progressive Date Rings)
    5. Tahap 3: Deteksi Indikasi Duplikat (dengan referensi kode) & Not Match
    """
    if hasattr(file, "seek"):
        file.seek(0)

    # Membaca file Excel mentah untuk mencari posisi header
    df_raw = pd.read_excel(file, header=None)

    # ------------------------------------------------------------------
    # 1. CLEANING DATA & DETEKSI HEADER DINAMIS
    # ------------------------------------------------------------------
    header_idx = -1
    for idx, row in df_raw.iterrows():
        row_str = " ".join([str(val).lower() for val in row])
        if "tanggal" in row_str and "qty" in row_str:
            header_idx = idx
            break

    if header_idx == -1:
        raise ValueError("Header tabel (Tanggal, Qty) tidak ditemukan. Pastikan format file benar.")

    if hasattr(file, "seek"):
        file.seek(0)

    df = pd.read_excel(file, header=header_idx)
    df.columns = [str(col).strip() for col in df.columns]

    # Membuang baris Saldo Awal dan baris kosong sepenuhnya
    df = df[~df.astype(str).apply(lambda x: x.str.contains("Saldo Awal", case=False, na=False)).any(axis=1)].copy()
    df = df.dropna(how="all").reset_index(drop=True)

    # Memastikan format kolom numerik tetap angka
    for col in ["Qty", "Trx Qty", "Saldo"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "Keterangan" not in df.columns or "Qty" not in df.columns:
        raise ValueError("Kolom wajib ('Keterangan' atau 'Qty') tidak ditemukan di tabel.")

    # Parsing kolom Tanggal untuk perhitungan selisih hari
    if "Tanggal" in df.columns:
        df["Tanggal_Parsed"] = pd.to_datetime(df["Tanggal"], dayfirst=True, errors="coerce")
    else:
        df["Tanggal_Parsed"] = pd.NaT

    # ------------------------------------------------------------------
    # 2. PREPARATION DATA
    # ------------------------------------------------------------------
    df["Status"] = ""
    df["Kode_Trx"] = df["Keterangan"].astype(str).str.extract(r"((?:MOV|MB)/[A-Za-z0-9/._-]+)")

    # Nilai absolut Qty dikali 10.000 menjadi bilangan bulat agar akurat untuk penjumlahan desimal
    df["Qty_Abs"] = df["Qty"].abs()
    df["Qty_Int"] = df["Qty_Abs"].apply(lambda x: int(round(x * 10000)) if pd.notna(x) else 0)

    # Klasifikasi jenis transaksi
    df["Jenis_Trx"] = df["Keterangan"].apply(deteksi_jenis_transaksi)
    df["Is_MOV_In"] = df["Jenis_Trx"] == "MOV_IN"
    df["Is_MB_Out"] = df["Jenis_Trx"] == "MB_OUT"
    df["Is_MOV_Out"] = df["Jenis_Trx"] == "MOV_OUT"
    df["Is_Target_Out"] = df["Is_MB_Out"] | df["Is_MOV_Out"]

    # Pelacakan baris yang sudah match & riwayat match per Qty (untuk deteksi duplikat di Tahap 3)
    sudah_match = set()
    riwayat_match_in = {}   # {qty_int: [(kode_mov_in, info_pasangan), ...]}
    riwayat_match_out = {}  # {qty_int: [(kode_out, info_pasangan), ...]}

    def ambil_kode(idx):
        kode = df.loc[idx, "Kode_Trx"]
        return str(kode) if pd.notna(kode) and str(kode).strip() else f"Baris-{idx + 1}"

    # ------------------------------------------------------------------
    # 3. TAHAP 1: MATCH 1 VS 1 (AKURASI TERTINGGI)
    # ------------------------------------------------------------------
    mask_valid = (df["Is_MOV_In"] | df["Is_Target_Out"]) & (df["Qty_Int"] > 0)
    unique_qtys = df.loc[mask_valid, "Qty_Int"].unique()

    for qty_int in unique_qtys:
        idx_in_list = df[(df["Is_MOV_In"]) & (df["Qty_Int"] == qty_int)].index.tolist()
        idx_out_list = df[(df["Is_Target_Out"]) & (df["Qty_Int"] == qty_int)].index.tolist()

        if not idx_in_list or not idx_out_list:
            continue

        # Buat semua pasangan kandidat dan urutkan berdasarkan selisih tanggal terkecil, lalu urutan baris
        pasangan_kandidat = []
        for i_in in idx_in_list:
            tgl_in = df.loc[i_in, "Tanggal_Parsed"]
            for i_out in idx_out_list:
                tgl_out = df.loc[i_out, "Tanggal_Parsed"]
                selisih = _hitung_selisih_hari(tgl_in, tgl_out)
                pasangan_kandidat.append((selisih, i_in, i_out))

        pasangan_kandidat.sort(key=lambda x: (x[0], x[1], x[2]))

        # Kunci pasangan 1:1 mulai dari yang jarak tanggalnya paling dekat
        for _, i_in, i_out in pasangan_kandidat:
            if i_in in sudah_match or i_out in sudah_match:
                continue

            sudah_match.add(i_in)
            sudah_match.add(i_out)

            kode_in = ambil_kode(i_in)
            kode_out = ambil_kode(i_out)

            df.loc[i_in, "Status"] = f"Match dgn {kode_out}"
            df.loc[i_out, "Status"] = f"Match dgn {kode_in}"

            riwayat_match_in.setdefault(qty_int, []).append((kode_in, kode_out))
            riwayat_match_out.setdefault(qty_int, []).append((kode_out, kode_in))

    # ------------------------------------------------------------------
    # 4. TAHAP 2: MATCH REKAP 1-TO-MANY & MANY-TO-1 (PROGRESSIVE DATE RINGS)
    # ------------------------------------------------------------------
    if aktifkan_rekap:
        lapisan_hari = _bangun_lapisan_tanggal(max_selisih_hari)

        def jalankan_rekap_satu_arah(list_induk, list_pecahan, batas_hari, induk_adalah_in):
            # Urutkan induk dari Qty terbesar ke terkecil agar rekap utama dicocokkan lebih dulu
            list_induk_urut = sorted(list_induk, key=lambda idx: (-df.loc[idx, "Qty_Int"], idx))

            for idx_induk in list_induk_urut:
                if idx_induk in sudah_match:
                    continue

                target_qty = int(df.loc[idx_induk, "Qty_Int"])
                tgl_induk = df.loc[idx_induk, "Tanggal_Parsed"]

                # Filter kandidat pecahan yang belum match, Qty < target, dan masuk rentang tanggal
                kandidat = []
                for idx_p in list_pecahan:
                    if idx_p in sudah_match:
                        continue
                    qty_p = int(df.loc[idx_p, "Qty_Int"])
                    if qty_p <= 0 or qty_p >= target_qty:
                        continue

                    tgl_p = df.loc[idx_p, "Tanggal_Parsed"]
                    selisih = _hitung_selisih_hari(tgl_induk, tgl_p)

                    if batas_hari is not None and selisih > batas_hari:
                        continue

                    kandidat.append((idx_p, qty_p, selisih))

                if len(kandidat) < 2:
                    continue

                # Prioritaskan kandidat dengan tanggal terdekat, lalu Qty terbesar
                kandidat.sort(key=lambda item: (item[2], -item[1], item[0]))

                idx_cocok = _cari_kombinasi_rekap(
                    target_qty=target_qty,
                    daftar_kandidat=kandidat,
                    max_pecahan=max_pecahan,
                    max_langkah=5000,
                )

                if idx_cocok:
                    sudah_match.add(idx_induk)
                    for idx_c in idx_cocok:
                        sudah_match.add(idx_c)

                    kode_induk = ambil_kode(idx_induk)
                    daftar_kode_pecahan = [ambil_kode(idx_c) for idx_c in idx_cocok]
                    ringkasan_kode_pecahan = _format_daftar_kode(daftar_kode_pecahan)

                    df.loc[idx_induk, "Status"] = f"Match Rekap ({len(idx_cocok)} trx): {ringkasan_kode_pecahan}"
                    for idx_c in idx_cocok:
                        df.loc[idx_c, "Status"] = f"Match Parsial dgn {kode_induk}"

                    # Catat induk ke riwayat match agar tetap terdeteksi jika ada duplikat di Tahap 3
                    info_rekap = f"Rekap {len(idx_cocok)} trx"
                    if induk_adalah_in:
                        riwayat_match_in.setdefault(target_qty, []).append((kode_induk, info_rekap))
                    else:
                        riwayat_match_out.setdefault(target_qty, []).append((kode_induk, info_rekap))

        for batas_hari in lapisan_hari:
            sisa_in = [i for i in df[(df["Is_MOV_In"]) & (df["Qty_Int"] > 0)].index if i not in sudah_match]
            sisa_out = [i for i in df[(df["Is_Target_Out"]) & (df["Qty_Int"] > 0)].index if i not in sudah_match]

            if not sisa_in or not sisa_out:
                break

            # Arah 1: 1 MOV Penambahan = Banyak MB / MOV Pengurangan
            jalankan_rekap_satu_arah(sisa_in, sisa_out, batas_hari, induk_adalah_in=True)

            # Perbarui sisa untuk arah sebaliknya
            sisa_in = [i for i in sisa_in if i not in sudah_match]
            sisa_out = [i for i in sisa_out if i not in sudah_match]

            if not sisa_in or not sisa_out:
                break

            # Arah 2: Banyak MOV Penambahan = 1 MB / MOV Pengurangan
            jalankan_rekap_satu_arah(sisa_out, sisa_in, batas_hari, induk_adalah_in=False)

    # ------------------------------------------------------------------
    # 5. TAHAP 3: DETEKSI INDIKASI DUPLIKAT & NOT MATCH (PALING AKHIR)
    # ------------------------------------------------------------------
    # Cek sisa MOV Penambahan
    sisa_mov_in = [i for i in df[df["Is_MOV_In"]].index if i not in sudah_match]
    for idx in sisa_mov_in:
        qty_int = int(df.loc[idx, "Qty_Int"])
        if qty_int > 0 and qty_int in riwayat_match_in:
            kode_ref, pasangan_ref = riwayat_match_in[qty_int][0]
            df.loc[idx, "Status"] = f"Indikasi Duplikat dgn {kode_ref} (Match: {pasangan_ref}) / Belum MB"
        else:
            df.loc[idx, "Status"] = "MOV Belum MB / Not Match"

    # Cek sisa MB Pengeluaran & MOV Pengurangan
    sisa_target_out = [i for i in df[df["Is_Target_Out"]].index if i not in sudah_match]
    for idx in sisa_target_out:
        qty_int = int(df.loc[idx, "Qty_Int"])
        if qty_int > 0 and qty_int in riwayat_match_out:
            kode_ref, pasangan_ref = riwayat_match_out[qty_int][0]
            df.loc[idx, "Status"] = f"Indikasi Duplikat dgn {kode_ref} (Match: {pasangan_ref}) / Belum PG"
        elif df.loc[idx, "Is_MB_Out"]:
            df.loc[idx, "Status"] = "MB belum di PG / Not Match"
        else:
            df.loc[idx, "Status"] = "MOV Pengurangan Not Match"

    # ------------------------------------------------------------------
    # 6. FINALISASI OUTPUT (HAPUS KOLOM BANTU)
    # ------------------------------------------------------------------
    kolom_bantu = [
        "Tanggal_Parsed",
        "Kode_Trx",
        "Qty_Abs",
        "Qty_Int",
        "Jenis_Trx",
        "Is_MOV_In",
        "Is_MB_Out",
        "Is_MOV_Out",
        "Is_Target_Out",
    ]
    df = df.drop(columns=[col for col in kolom_bantu if col in df.columns])

    return df
