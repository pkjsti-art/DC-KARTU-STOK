import streamlit as st
import pandas as pd
from io import BytesIO
from data_processor import process_data

# Konfigurasi Halaman
st.set_page_config(
    page_title="Data Control Kartu Stok", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# Load custom CSS
def local_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except Exception:
        pass

local_css("style.css")

# Dashboard UI
st.title("🌐 Data Control Kartu Stok")
st.markdown("Sistem Rekonsiliasi Otomatis Transaksi Gudang (MOV & MB)")

# Fungsi untuk konversi dataframe ke excel
def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Hasil_Crosscheck')
    processed_data = output.getvalue()
    return processed_data

# Sidebar
with st.sidebar:
    st.header("⚙️ Crosscheck Kartu Stok")
    st.markdown("Silakan unggah file kartu stok perusahaan Anda.")
    
    uploaded_file = st.file_uploader("Import Data Kartu Stok (Excel)", type=['xlsx', 'xls'])
    
    proses_btn = st.button("🚀 Proses Data")

# Reset session state jika file baru diunggah atau dihapus
if uploaded_file is None:
    if 'df_result' in st.session_state:
        del st.session_state['df_result']
    st.info("👈 Silakan unggah data di sidebar untuk memulai.")
else:
    # Logika Proses Data saat tombol diklik
    if proses_btn:
        with st.spinner("Memproses sinkronisasi data..."):
            try:
                # Simpan hasil ke session_state agar tidak hilang saat reload
                st.session_state['df_result'] = process_data(uploaded_file)
            except Exception as e:
                st.error(f"Terjadi kesalahan saat memproses data: {e}")

    # Menampilkan hasil jika ada di session_state
    if 'df_result' in st.session_state:
        st.success("✅ Proses Crosscheck Selesai!")
        st.subheader("📋 Tabel Hasil Cek Data")
        
        df_result = st.session_state['df_result']
        
        # Menampilkan tabel interaktif
        st.dataframe(df_result, use_container_width=True, height=600)
        
        # Tombol Download
        excel_data = to_excel(df_result)
        st.download_button(
            label="📥 Download Data Hasil Crosscheck",
            data=excel_data,
            file_name="Hasil_Crosscheck_Kartu_Stok.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
