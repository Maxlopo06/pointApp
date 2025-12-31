import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date

# --- CONFIGURATION ---
SPREADSHEET_NAME = "Applikasi Point DB" # Make sure this matches your Sheet name exactly

# --- SETUP CREDENTIALS ---
# We use st.cache_resource so we don't reconnect every time you click a button
@st.cache_resource
def connect_to_gsheets():
    # Define the scope
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Load credentials from Streamlit Secrets (Best Practice for Online)
    # OR fallback to local file for testing
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            # Local testing: Ensure 'credentials.json' is in the same folder
            creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        
        client = gspread.authorize(creds)
        sheet = client.open(SPREADSHEET_NAME)
        return sheet
    except Exception as e:
        st.error(f"❌ Connection Error: {e}")
        return None

# --- HELPER FUNCTIONS ---
def load_data(sheet):
    """Reads data from the 3 tabs."""
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
            df_log['No'] = pd.to_numeric(df_log['No'])
        
        return df_list, df_log
    except Exception as e:
        st.error(f"Error reading worksheets: {e}")
        return pd.DataFrame(), pd.DataFrame()

def add_log_entry(sheet, date_val, activity, point, approval):
    """Appends a new row to LogActivity tab."""
    ws_log = sheet.worksheet("LogActivity")
    
    # Calculate new ID
    # Get all values in column 1 (No) to find max
    col_values = ws_log.col_values(1)
    # Filter for numeric values only (skip header)
    ids = [int(x) for x in col_values[1:] if x.isdigit()]
    new_id = max(ids) + 1 if ids else 1
    
    # Row to append
    # Note: We convert date to string for JSON compatibility
    row = [new_id, str(date_val), activity, point, approval]
    
    # Append
    ws_log.append_row(row)
    
    return True

def update_recap(sheet, df_log):
    """Recalculates totals and overwrites RecapPoint tab."""
    if df_log.empty:
        return

    # Group in Pandas
    recap = df_log.groupby('Date')['Point'].sum().reset_index()
    recap.rename(columns={'Point': 'Rekap Point'}, inplace=True)
    recap.insert(0, 'No', range(1, len(recap) + 1))
    
    # Convert dates to string for upload
    recap['Date'] = recap['Date'].astype(str)
    
    # Update Sheet
    ws_recap = sheet.worksheet("RecapPoint")
    ws_recap.clear() # Clear old data
    
    # Prepare data: [Header] + [Rows]
    data_to_upload = [recap.columns.tolist()] + recap.values.tolist()
    ws_recap.update(data_to_upload)

# --- APP UI ---
st.title("🏆 Daily Activity Point Tracker (Online)")

sheet = connect_to_gsheets()

if sheet:
    df_list, df_log = load_data(sheet)
    
    # -- SIDEBAR --
    st.sidebar.header("Add Activity")
    sel_date = st.sidebar.date_input("Date", date.today())
    
    if not df_list.empty:
        # Helper to find points
        activity_map = dict(zip(df_list['Activity'], df_list['Points']))
        sel_activity = st.sidebar.selectbox("Activity", df_list['Activity'].unique())
        sel_approval = st.sidebar.selectbox("Approval", ["Good", "Average", "Not Good"])
        
        if st.sidebar.button("Submit Log"):
            points = int(activity_map[sel_activity])
            
            with st.spinner("Saving to Google Sheets..."):
                # 1. Add to GSheet
                add_log_entry(sheet, sel_date, sel_activity, points, sel_approval)
                
                # 2. Refresh Data locally to calculate recap
                # (We cheat a bit here by manually adding to our local DF to save a read)
                new_row = {'No': 999, 'Date': sel_date, 'Activity': sel_activity, 'Point': points, 'Approval': sel_approval}
                df_log = pd.concat([df_log, pd.DataFrame([new_row])], ignore_index=True)
                
                # 3. Update Recap Sheet
                update_recap(sheet, df_log)
                
            st.success(f"Saved: {sel_activity}")
            st.rerun() # Refresh to show new data
    else:
        st.warning("Could not load Activity List from Google Sheet.")

    # -- MAIN VIEW --
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Log History")
        if not df_log.empty:
            st.dataframe(df_log.sort_values('Date', ascending=False), use_container_width=True)
            
    with col2:
        st.subheader("Points Recap")
        # Read recap fresh or calculate
        ws_recap = sheet.worksheet("RecapPoint")
        recap_data = ws_recap.get_all_records()
        df_recap = pd.DataFrame(recap_data)
        if not df_recap.empty:
            st.dataframe(df_recap, use_container_width=True, hide_index=True)
            st.bar_chart(df_recap.set_index('Date')['Rekap Point'])