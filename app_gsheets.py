import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date
import datetime

# --- CONFIGURATION ---
SPREADSHEET_NAME = "Applikasi Point DB" 

# --- SETUP CREDENTIALS ---
@st.cache_resource
def connect_to_gsheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        
        client = gspread.authorize(creds)
        sheet = client.open(SPREADSHEET_NAME)
        return sheet
    except Exception as e:
        st.error(f"❌ Connection Error: {e}")
        return None

# --- HELPER FUNCTIONS ---
def load_data(sheet):
    try:
        # 1. List Activity
        ws_list = sheet.worksheet("ListActivity")
        list_data = ws_list.get_all_records()
        df_list = pd.DataFrame(list_data)
        
        # 2. Log Activity
        ws_log = sheet.worksheet("LogActivity")
        log_data = ws_log.get_all_records()
        df_log = pd.DataFrame(log_data)
        
        # Ensure correct types
        if not df_log.empty:
            df_log['Date'] = pd.to_datetime(df_log['Date']).dt.date
            # Pastikan kolom Point dibaca sebagai angka
            df_log['Point'] = pd.to_numeric(df_log['Point'], errors='coerce').fillna(0)
            df_log['No'] = pd.to_numeric(df_log['No'], errors='coerce')
        
        return df_list, df_log
    except Exception as e:
        st.error(f"Error reading worksheets: {e}")
        return pd.DataFrame(), pd.DataFrame()

def add_log_entry(sheet, date_val, activity, point, approval):
    ws_log = sheet.worksheet("LogActivity")
    col_values = ws_log.col_values(1)
    ids = [int(x) for x in col_values[1:] if x.isdigit()]
    new_id = max(ids) + 1 if ids else 1
    
    row = [new_id, str(date_val), activity, point, approval]
    ws_log.append_row(row)
    return True

def update_recap(sheet, df_log):
    if df_log.empty:
        return

    # Group by Date
    recap = df_log.groupby('Date')['Point'].sum().reset_index()
    recap.rename(columns={'Point': 'Rekap Point'}, inplace=True)
    recap.insert(0, 'No', range(1, len(recap) + 1))
    
    recap['Date'] = recap['Date'].astype(str)
    
    ws_recap = sheet.worksheet("RecapPoint")
    ws_recap.clear()
    data_to_upload = [recap.columns.tolist()] + recap.values.tolist()
    ws_recap.update(data_to_upload)

# --- APP UI ---
st.set_page_config(page_title="Point Tracker", page_icon="🏆") # Tab title
st.title("🏆 Daily Activity Point Tracker")

sheet = connect_to_gsheets()

if sheet:
    df_list, df_log = load_data(sheet)
    
    # --- DASHBOARD SUMMARY (BAGIAN BARU) ---
    st.markdown("---") # Garis pemisah
    if not df_log.empty:
        # 1. Total Semua Poin
        total_points = int(df_log['Point'].sum())
        
        # 2. Total Poin Bulan Ini
        today = date.today()
        # Filter data bulan ini
        # Kita convert 'Date' di df_log ke datetime dulu untuk filtering
        df_log_temp = df_log.copy()
        df_log_temp['DateObj'] = pd.to_datetime(df_log_temp['Date'])
        current_month_mask = (df_log_temp['DateObj'].dt.month == today.month) & (df_log_temp['DateObj'].dt.year == today.year)
        monthly_points = int(df_log_temp.loc[current_month_mask, 'Point'].sum())

        # Tampilkan Metrics Berdampingan
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("💰 Total Poin (Semua)", f"{total_points:,}")
        col_m2.metric("📅 Poin Bulan Ini", f"{monthly_points:,}")
        col_m3.metric("📝 Total Aktivitas", len(df_log))
    else:
        st.info("Belum ada data poin.")
    st.markdown("---")

    # --- SIDEBAR INPUT ---
    st.sidebar.header("Add Activity")
    sel_date = st.sidebar.date_input("Date", date.today())
    
    if not df_list.empty:
        activity_map = dict(zip(df_list['Activity'], df_list['Points']))
        sel_activity = st.sidebar.selectbox("Activity", df_list['Activity'].unique())
        sel_approval = st.sidebar.selectbox("Approval", ["Good", "Average", "Not Good"])
        
        if st.sidebar.button("Submit Log"):
            points = int(activity_map[sel_activity])
            
            with st.spinner("Saving to Google Sheets..."):
                add_log_entry(sheet, sel_date, sel_activity, points, sel_approval)
                
                # Update local df sementara agar UI langsung berubah tanpa reload berat
                new_row = {'No': 999, 'Date': sel_date, 'Activity': sel_activity, 'Point': points, 'Approval': sel_approval}
                df_log = pd.concat([df_log, pd.DataFrame([new_row])], ignore_index=True)
                
                update_recap(sheet, df_log)
                
            st.success(f"Saved: {sel_activity} ({points} pts)")
            st.rerun()
    else:
        st.warning("Could not load Activity List.")

    # --- TABEL DATA ---
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📜 Riwayat Aktivitas")
        if not df_log.empty:
            # Tampilkan kolom yang relevan saja agar rapi
            display_cols = ['Date', 'Activity', 'Point', 'Approval']
            st.dataframe(
                df_log.sort_values('Date', ascending=False)[display_cols], 
                use_container_width=True,
                hide_index=True
            )
            
    with col2:
        st.subheader("📊 Grafik Harian")
        ws_recap = sheet.worksheet("RecapPoint")
        recap_data = ws_recap.get_all_records()
        df_recap = pd.DataFrame(recap_data)
        if not df_recap.empty:
            # Simple Bar Chart
            st.bar_chart(df_recap.set_index('Date')['Rekap Point'])
            
            # Tampilkan tabel kecil di bawah grafik
            st.dataframe(df_recap[['Date', 'Rekap Point']], hide_index=True)
