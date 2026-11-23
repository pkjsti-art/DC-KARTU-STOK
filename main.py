import streamlit as st
import pandas as pd
from io import BytesIO
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.hyperlink import Hyperlink
from data_processor import (
    process_data,
    deteksi_jenis_transaksi,
    deteksi_kategori_status,
)

# Mengizinkan Pandas Styler merender tabel besar tanpa error batas sel
pd.set_option("styler.render.max_elements", 1000000)

# Konfigurasi Halaman
st.set_page_config(
    page_title="Data Control Kartu Stok",
    layout="wide",
    initial_sidebar_state="expanded",
)


# Load custom CSS
def local_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except Exception:
        pass


local_css("style.css")


# ------------------------------------------------------------------
# KONFIGURASI WARNA WEB (DARK CYBER THEME) & EXCEL (SOFT PASTEL)
# ------------------------------------------------------------------
WARNA_BARIS_WEB = {
    "MOV_IN": "background-color: #0e2a47; color: #e0f2fe;",
    "MB_OUT": "background-color: #3b2314; color: #ffedd5;",
    "MOV_OUT": "background-color: #2e1a47; color: #f3e8ff;",
    "LAINNYA": "background-color: #161e2e; color: #cbd5e1;",
}

WARNA_STATUS_WEB = {
    "MATCH_1_1": "background-color: #14532d; color: #86efac; font-weight: bold;",
    "MATCH_REKAP": "background-color: #115e59; color: #5eead4; font-weight: bold;",
    "DUPLIKAT": "background-color: #713f12; color: #fde047; font-weight: bold;",
    "NOT_MATCH": "background-color: #7f1d1d; color: #fca5a5; font-weight: bold;",
}

WARNA_BARIS_EXCEL = {
    "MOV_IN": "E0F2FE",   # Biru lembut
    "MB_OUT": "FFEDD5",   # Oranye lembut
    "MOV_OUT": "F3E8FF",  # Ungu lembut
    "LAINNYA": "FFFFFF",  # Putih netral
}

WARNA_STATUS_EXCEL = {
    "MATCH_1_1": ("DCFCE7", "166534"),    # Hijau lembut, teks hijau tua
    "MATCH_REKAP": ("CCFBF1", "115E59"),  # Tosca lembut, teks tosca tua
    "DUPLIKAT": ("FEF9C3", "854D0E"),     # Kuning lembut, teks cokelat tua
    "NOT_MATCH": ("FEE2E2", "991B1B"),    # Merah lembut, teks merah tua
}


def warnai_tabel_web(row):
    """Memberi warna latar per baris (jenis MOV/MB), penegasan ID Match, dan warna khusus kolom Status."""
    jenis = deteksi_jenis_transaksi(row.get("Keterangan", ""))
    gaya_baris = WARNA_BARIS_WEB.get(jenis, WARNA_BARIS_WEB["LAINNYA"])
    gaya_sel = [gaya_baris] * len(row)

    if "ID Match" in row.index and str(row["ID Match"]).strip():
        posisi_id = row.index.get_loc("ID Match")
        gaya_sel[posisi_id] = f"{gaya_baris} font-weight: bold; text-align: center;"

    if "Status" in row.index:
        kategori_status = deteksi_kategori_status(row["Status"])
        if kategori_status in WARNA_STATUS_WEB:
            posisi_status = row.index.get_loc("Status")
            gaya_sel[posisi_status] = WARNA_STATUS_WEB[kategori_status]

    return gaya_sel


def format_angka_tampil(val):
    """Memformat angka di tabel web agar rapi tanpa nol desimal berlebih."""
    if pd.isna(val):
        return ""
    try:
        angka = float(val)
        if angka.is_integer():
            return f"{int(angka):,}"
        return f"{angka:,.4f}".rstrip("0").rstrip(".")
    except (ValueError, TypeError):
        return val


def to_excel_berwarna(df, link_targets=None):
    """
    Mengonversi hasil crosscheck ke file Excel (.xlsx) lengkap dengan:
    - Warna baris (jenis transaksi) & warna sel Status
    - Hyperlink internal antar-baris pada kolom Status
    - Kolom ID Match yang rapi & rata tengah
    - Format angka murni, freeze header, dan auto-filter
    """
    if link_targets is None:
        link_targets = {}

    sheet_name = "Hasil_Crosscheck"
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        ws = writer.sheets[sheet_name]

        # Gaya dasar
        header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        font_normal = Font(name="Calibri", size=10, color="0F172A")
        font_id_match = Font(name="Calibri", size=10, bold=True, color="0F172A")
        align_center = Alignment(horizontal="center", vertical="center")
        thin_side = Side(border_style="thin", color="CBD5E1")
        cell_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        # Cari indeks kolom penting (berbasis 1 untuk openpyxl)
        kolom_list = list(df.columns)
        idx_col_status = kolom_list.index("Status") + 1 if "Status" in kolom_list else -1
        idx_col_id_match = kolom_list.index("ID Match") + 1 if "ID Match" in kolom_list else -1
        idx_col_keterangan = kolom_list.index("Keterangan") + 1 if "Keterangan" in kolom_list else -1
        status_col_letter = get_column_letter(idx_col_status) if idx_col_status != -1 else "A"

        # 1. Styling Baris Header
        for col_idx in range(1, len(kolom_list) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = align_center
            cell.border = cell_border
        ws.row_dimensions[1].height = 24

        # 2. Styling Setiap Baris Data & Pemasangan Hyperlink
        for row_pos, (_, row_data) in enumerate(df.iterrows()):
            row_num = row_pos + 2  # Baris 1 adalah header Excel
            jenis = deteksi_jenis_transaksi(row_data.get("Keterangan", ""))
            kode_warna_baris = WARNA_BARIS_EXCEL.get(jenis, "FFFFFF")
            row_fill = PatternFill(start_color=kode_warna_baris, end_color=kode_warna_baris, fill_type="solid")

            status_teks = str(row_data.get("Status", "")) if pd.notna(row_data.get("Status", "")) else ""
            id_match_teks = str(row_data.get("ID Match", "")) if pd.notna(row_data.get("ID Match", "")) else ""
            kategori_status = deteksi_kategori_status(status_teks)

            for col_idx in range(1, len(kolom_list) + 1):
                cell = ws.cell(row=row_num, column=col_idx)
                cell.border = cell_border

                if col_idx == idx_col_status and kategori_status in WARNA_STATUS_EXCEL:
                    bg_status, fg_status = WARNA_STATUS_EXCEL[kategori_status]
                    cell.fill = PatternFill(start_color=bg_status, end_color=bg_status, fill_type="solid")

                    # Pasang hyperlink internal jika baris memiliki target lompatan
                    if row_pos in link_targets:
                        target_excel_row = int(link_targets[row_pos]) + 2
                        if status_teks.startswith("Match Rekap"):
                            tooltip_text = (
                                f"Lompat ke pecahan pertama (Baris {target_excel_row}). "
                                f"Filter ID Match '{id_match_teks}' untuk melihat semua pasangannya."
                            )
                        elif kategori_status == "DUPLIKAT":
                            tooltip_text = (
                                f"Lompat ke transaksi referensi (Baris {target_excel_row}). "
                                f"Filter ID Match '{id_match_teks}' untuk membandingkan grupnya."
                            )
                        else:
                            tooltip_text = f"Klik untuk lompat ke pasangan (Baris {target_excel_row})"

                        cell.hyperlink = Hyperlink(
                            ref=cell.coordinate,
                            location=f"{sheet_name}!{status_col_letter}{target_excel_row}",
                            tooltip=tooltip_text,
                        )
                        cell.font = Font(
                            name="Calibri",
                            size=10,
                            bold=True,
                            color=fg_status,
                            underline="single",
                        )
                    else:
                        cell.font = Font(name="Calibri", size=10, bold=True, color=fg_status)

                elif col_idx == idx_col_id_match:
                    cell.fill = row_fill
                    cell.font = font_id_match
                    cell.alignment = align_center

                else:
                    cell.fill = row_fill
                    cell.font = font_normal

        # 3. Auto-fit Lebar Kolom
        for col_idx, col_name in enumerate(kolom_list, start=1):
            col_letter = get_column_letter(col_idx)
            panjang_maks = len(str(col_name))
            sampel = df[col_name].astype(str).head(500)
            if not sampel.empty:
                panjang_maks = max(panjang_maks, int(sampel.str.len().max()))

            if col_idx == idx_col_id_match:
                ws.column_dimensions[col_letter].width = max(12, panjang_maks + 3)
            else:
                batas_lebar = 55 if col_idx in (idx_col_status, idx_col_keterangan) else 28
                ws.column_dimensions[col_letter].width = min(panjang_maks + 4, batas_lebar)

        # 4. Freeze Header & Aktifkan Auto-Filter
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    return output.getvalue()


# ------------------------------------------------------------------
# DASHBOARD UI
# ------------------------------------------------------------------
st.title("🌐 Data Control Kartu Stok")
st.markdown("Sistem Rekonsiliasi Otomatis Transaksi Gudang (MOV & MB — 1:1 & Rekap/Parsial)")

# Sidebar
with st.sidebar:
    st.header("⚙️ Crosscheck Kartu Stok")
    st.markdown("Silakan unggah file kartu stok perusahaan Anda.")

    uploaded_file = st.file_uploader("Import Data Kartu Stok (Excel)", type=["xlsx", "xls"])

    st.divider()
    st.subheader("🧩 Pengaturan Match Rekap")
    aktifkan_rekap = st.checkbox(
        "Aktifkan Match Rekap (1-to-Many & Many-to-1)",
        value=True,
        help="Mencocokkan sisa transaksi yang tidak match 1:1 dengan menjumlahkan beberapa transaksi detail.",
    )

    opsi_hari = {
        "Tanpa Batas (Prioritas Tanggal Terdekat)": None,
        "0 Hari (Hanya Tanggal Sama)": 0,
        "Maksimal ± 3 Hari": 3,
        "Maksimal ± 7 Hari": 7,
        "Maksimal ± 14 Hari": 14,
        "Maksimal ± 30 Hari": 30,
    }
    pilihan_hari_label = st.selectbox(
        "Batas Selisih Tanggal Rekap",
        options=list(opsi_hari.keys()),
        index=0,
        disabled=not aktifkan_rekap,
        help="Sistem selalu mencocokkan selisih hari terkecil lebih dulu (0 hari → 3 → 7 → 14 → 30 → bebas).",
    )
    max_selisih_hari = opsi_hari[pilihan_hari_label]

    max_pecahan = st.slider(
        "Maksimal Pecahan per 1 Rekap",
        min_value=2,
        max_value=15,
        value=8,
        disabled=not aktifkan_rekap,
        help="Jumlah maksimal transaksi detail yang digabungkan untuk 1 transaksi rekap.",
    )

    st.divider()
    proses_btn = st.button("🚀 Proses Data")

# Reset session state jika file dihapus atau berganti file baru
if uploaded_file is None:
    for key in ("df_result", "link_targets", "file_signature"):
        if key in st.session_state:
            del st.session_state[key]
    st.info("👈 Silakan unggah data kartu stok di sidebar untuk memulai.")
else:
    signature_sekarang = f"{uploaded_file.name}_{uploaded_file.size}"
    if st.session_state.get("file_signature") != signature_sekarang:
        st.session_state["file_signature"] = signature_sekarang
        for key in ("df_result", "link_targets"):
            if key in st.session_state:
                del st.session_state[key]

    # Logika Proses Data saat tombol diklik
    if proses_btn:
        with st.spinner("Memproses sinkronisasi 1:1, match rekap berlapis, ID Match, dan deteksi duplikat..."):
            try:
                df_hasil, peta_link = process_data(
                    uploaded_file,
                    aktifkan_rekap=aktifkan_rekap,
                    max_selisih_hari=max_selisih_hari,
                    max_pecahan=max_pecahan,
                )
                st.session_state["df_result"] = df_hasil
                st.session_state["link_targets"] = peta_link
            except Exception as e:
                st.error(f"Terjadi kesalahan saat memproses data: {e}")

    # Menampilkan hasil jika ada di session_state
    if "df_result" in st.session_state:
        df_result = st.session_state["df_result"]
        link_targets = st.session_state.get("link_targets", {})
        st.success("✅ Proses Crosscheck Selesai!")

        # ----------------------------------------------------------
        # KARTU RINGKASAN (SUMMARY METRICS)
        # ----------------------------------------------------------
        kategori_series = df_result["Status"].apply(deteksi_kategori_status)
        jml_total = len(df_result)
        jml_match_1_1 = int((kategori_series == "MATCH_1_1").sum())
        jml_match_rekap = int((kategori_series == "MATCH_REKAP").sum())
        jml_duplikat = int((kategori_series == "DUPLIKAT").sum())
        jml_not_match = int((kategori_series == "NOT_MATCH").sum())

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("📄 Total Baris", f"{jml_total:,}")
        col2.metric("✅ Match 1:1", f"{jml_match_1_1:,}")
        col3.metric("🧩 Match Rekap/Parsial", f"{jml_match_rekap:,}")
        col4.metric("⚠️ Indikasi Duplikat", f"{jml_duplikat:,}")
        col5.metric("❌ Not Match", f"{jml_not_match:,}")

        st.subheader("📋 Tabel Hasil Cek Data")

        # ----------------------------------------------------------
        # LEGENDA WARNA
        # ----------------------------------------------------------
        st.markdown(
            """
            <div class="legend-container">
                <span class="legend-title">Warna Baris:</span>
                <span class="legend-badge" style="background:#0e2a47; color:#e0f2fe;">MOV Penambahan</span>
                <span class="legend-badge" style="background:#3b2314; color:#ffedd5;">MB Pengeluaran</span>
                <span class="legend-badge" style="background:#2e1a47; color:#f3e8ff;">MOV Pengurangan</span>
                <span class="legend-badge" style="background:#161e2e; color:#cbd5e1;">Transaksi Lainnya</span>
                <span class="legend-title" style="margin-left:10px;">Status:</span>
                <span class="legend-badge" style="background:#14532d; color:#86efac;">Match 1:1 (M-xxx)</span>
                <span class="legend-badge" style="background:#115e59; color:#5eead4;">Match Rekap / Parsial (R-xxx)</span>
                <span class="legend-badge" style="background:#713f12; color:#fde047;">Indikasi Duplikat</span>
                <span class="legend-badge" style="background:#7f1d1d; color:#fca5a5;">Not Match</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ----------------------------------------------------------
        # FILTER CEPAT STATUS & PELACAK GRUP ID MATCH
        # ----------------------------------------------------------
        col_f1, col_f2 = st.columns([2, 1])

        opsi_filter = [
            "Semua Data",
            "Hanya Not Match",
            "Hanya Indikasi Duplikat",
            "Hanya Match Rekap / Parsial",
            "Hanya Match 1:1",
            "Hanya Transaksi Lainnya (Status Kosong)",
        ]
        pilihan_filter = col_f1.selectbox("🔍 Filter Cepat Status", opsi_filter, index=0)

        daftar_id = sorted(
            [str(x) for x in df_result["ID Match"].dropna().unique() if str(x).strip()]
        )
        pilihan_id = col_f2.selectbox(
            "🏷️ Lacak Grup ID Match",
            options=["Semua ID"] + daftar_id,
            index=0,
            help="Pilih satu ID Match (misal R-001 atau M-005) untuk menampilkan seluruh pasangan dalam satu grup.",
        )

        peta_filter = {
            "Hanya Not Match": "NOT_MATCH",
            "Hanya Indikasi Duplikat": "DUPLIKAT",
            "Hanya Match Rekap / Parsial": "MATCH_REKAP",
            "Hanya Match 1:1": "MATCH_1_1",
            "Hanya Transaksi Lainnya (Status Kosong)": "KOSONG",
        }

        if pilihan_id != "Semua ID":
            # Menampilkan seluruh baris dalam grup ID Match yang dipilih agar audit pasangan lengkap
            df_tampil = df_result[df_result["ID Match"] == pilihan_id]
            if "Qty" in df_tampil.columns:
                selisih_grup = df_tampil["Qty"].sum()
                st.caption(
                    f"Menampilkan **{len(df_tampil)} baris** untuk grup **{pilihan_id}** "
                    f"(Netto Qty grup: **{format_angka_tampil(selisih_grup)}**)"
                )
        elif pilihan_filter == "Semua Data":
            df_tampil = df_result
        else:
            df_tampil = df_result[kategori_series == peta_filter[pilihan_filter]]

        # Menampilkan tabel interaktif berwarna
        if df_tampil.empty:
            st.info(f"Tidak ada baris transaksi untuk filter '{pilihan_filter}'.")
        else:
            format_kolom_angka = {
                col: format_angka_tampil
                for col in ["Qty", "Trx Qty", "Saldo"]
                if col in df_tampil.columns
            }
            styler = df_tampil.style.apply(warnai_tabel_web, axis=1)
            if format_kolom_angka:
                styler = styler.format(format_kolom_angka)

            st.dataframe(styler, use_container_width=True, height=600)

        # Tombol Download (selalu mengunduh seluruh hasil lengkap berwarna + hyperlink Excel)
        excel_data = to_excel_berwarna(df_result, link_targets)
        st.download_button(
            label="📥 Download Data Hasil Crosscheck (Excel Berwarna + Hyperlink)",
            data=excel_data,
            file_name="Hasil_Crosscheck_Kartu_Stok.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
