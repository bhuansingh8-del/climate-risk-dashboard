import streamlit as st
import pandas as pd
import geopandas as gpd
import plotly.express as px
import os
import glob
import warnings
import difflib

# 1. Suppress all warnings (Fixes the "use_container_width" logs)
warnings.filterwarnings("ignore")
os.environ["PYTHONWARNINGS"] = "ignore"

# ================= CONFIGURATION =================
PAGE_TITLE = "TRI Dashboard (IDS-DRR)"
AVAILABLE_YEARS = [2026]

st.set_page_config(page_title=PAGE_TITLE, layout="wide")

# ================= CUSTOM CSS =================
st.markdown("""
<style>
    .stApp {
        background-color: white;
        color: black;
    }
    div[role="radiogroup"] > label {
        font-size: 20px !important;
        font-weight: bold !important;
        padding: 10px 25px;
        border: 2px solid #e0e0e0;
        border-radius: 8px;
        margin-right: 15px;
        background-color: white;
        color: black;
    }
    div[role="radiogroup"] {
        display: flex;
        flex-direction: row;
        gap: 15px;
    }
</style>
""", unsafe_allow_html=True)

# ================= DATA LOADING FUNCTIONS =================

@st.cache_data
def load_state_files():
    """Finds all the detailed prediction Excel files."""
    files = glob.glob("*_DETAILED_PREDICTIONS_*.xlsx")
    state_map = {}
    for f in files:
        # Extract state name: "ASSAM_DETAILED_PREDICTIONS..." -> "ASSAM"
        state_name = os.path.basename(f).split("_DETAILED")[0].replace("_", " ")
        state_map[state_name] = f
    return state_map

@st.cache_data
def load_shapefile():
    """
    AUTO-DETECTS the shapefile. 
    It looks for ANY file ending in .shp in the folder.
    """
    # Find any .shp file
    shp_files = glob.glob("*.shp")
    
    if not shp_files:
        st.error("🚨 CRITICAL ERROR: No .shp file found in GitHub repository.")
        st.write("Files found in folder:", os.listdir("."))
        return None
    
    # Use the first one found (e.g., DISTRICT_BOUNDARY_CLEAN.shp)
    map_path = shp_files[0]
    
    try:
        gdf = gpd.read_file(map_path)
        
        # Ensure Lat/Lon projection
        if gdf.crs != "EPSG:4326":
            gdf = gdf.to_crs(epsg=4326)
            
        # Clean Names
        gdf['STATE_CLEAN'] = gdf['STATE'].str.upper().str.strip()
        gdf['DIST_CLEAN'] = gdf['District'].str.upper().str.strip()
        return gdf
    except Exception as e:
        st.error(f"Error reading map file: {e}")
        return None

@st.cache_data
def load_all_districts_data(file_path):
    try:
        return pd.read_excel(file_path, sheet_name=None)
    except:
        return None

def get_risk_label(prob, type='flood'):
    if type == 'flood':
        if prob < 20: return "Low"
        elif prob < 40: return "Moderate"
        elif prob < 70: return "High"
        else: return "Very High"
    elif type == 'heat':
        if prob < 20: return "Low"
        elif prob < 40: return "Moderate"
        elif prob < 70: return "Extreme"
        else: return "Very Extreme"
    return "Unknown"

def calculate_risk_months(df):
    df['Month'] = df['Date'].dt.month_name()
    high_heat = df[df['Heat_Prob_%'] > 40]['Month'].unique()
    high_flood = df[df['Extreme_Rain_Prob_%'] > 40]['Month'].unique()
    return list(high_heat), list(high_flood)

# ================= MAIN DASHBOARD =================

def main():
    st.title(f"🌍 {PAGE_TITLE}")
    
    # --- 1. SETUP ---
    available_states = load_state_files()
    if not available_states:
        st.error("🚨 No prediction data found. Please upload your Excel files.")
        st.stop()

    st.sidebar.header("📍 Settings")
    selected_state = st.sidebar.selectbox("Select State", list(available_states.keys()))
    state_file_path = available_states[selected_state]

    with st.spinner("Loading Data..."):
        all_districts_data = load_all_districts_data(state_file_path)
    
    if not all_districts_data:
        st.error("Could not load state data.")
        st.stop()
        
    district_list = list(all_districts_data.keys())

    # --- 2. TOP CONTROLS ---
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        months = ['January', 'February', 'March', 'April', 'May', 'June', 
                  'July', 'August', 'September', 'October', 'November', 'December']
        selected_month = st.selectbox("📅 Select Month", months)
        
    with col2:
        week_of_month = st.selectbox("📆 Select Week", ["Week 1", "Week 2", "Week 3", "Week 4"])
        month_idx = months.index(selected_month)
        week_of_year = (month_idx * 4) + int(week_of_month.split(" ")[1])
        if week_of_year > 52: week_of_year = 52

    with col3:
        map_view = st.radio("Visualize Risk Type:", ["Flood Risk", "Heat Risk"], horizontal=True)

    # --- 3. MAP LOGIC (AUTO-DETECT) ---
    gdf = load_shapefile()
    
    if gdf is not None:
        # === SMART MATCHING ===
        map_states = gdf['STATE_CLEAN'].unique()
        clean_selected = selected_state.upper().strip()
        
        # Fuzzy match to handle "Maharastra" vs "Maharashtra"
        matches = difflib.get_close_matches(clean_selected, map_states, n=1, cutoff=0.6)
        
        if matches:
            matched_state = matches[0]
            # Filter Map
            state_gdf = gdf[gdf['STATE_CLEAN'] == matched_state].copy()
            
            if matched_state != clean_selected:
                st.toast(f"Map matched: '{selected_state}' ➡️ '{matched_state}'")
        else:
            st.error(f"❌ Could not find map boundaries for '{selected_state}'")
            st.write("Available Map States:", map_states)
            state_gdf = pd.DataFrame()

        if not state_gdf.empty:
            week_risk_data = []
            
            for dist_name, df in all_districts_data.items():
                row = df[df['Week'] == week_of_year]
                if not row.empty:
                    r = row.iloc[0]
                    heat_val = r['Heat_Prob_%']
                    flood_val = r['Extreme_Rain_Prob_%']
                    
                    week_risk_data.append({
                        'District_Match': dist_name.upper().strip(),
                        'Heat_Val': heat_val,
                        'Flood_Val': flood_val,
                        'Heat_Label': get_risk_label(heat_val, 'heat'),
                        'Flood_Label': get_risk_label(flood_val, 'flood'),
                        'Rain_Poss': f"{int(flood_val)}%"
                    })

            if week_risk_data:
                risk_df = pd.DataFrame(week_risk_data)
                
                # === SAFE MERGE ===
                map_data = state_gdf.merge(risk_df, left_on='DIST_CLEAN', right_on='District_Match', how='left')
                map_data = gpd.GeoDataFrame(map_data, geometry='geometry')
                
                # === SAFE FILLNA ===
                cols_to_fill = ['Heat_Val', 'Flood_Val', 'Heat_Label', 'Flood_Label', 'Rain_Poss']
                for col in cols_to_fill:
                    if col in map_data.columns:
                        if 'Val' in col:
                            map_data[col] = map_data[col].fillna(0)
                        else:
                            map_data[col] = map_data[col].fillna("No Data")
                
                # Colors
                if map_view == "Heat Risk":
                    color_col = 'Heat_Val'
                    colors = "Reds"
                    hover_label = 'Heat_Label'
                else:
                    color_col = 'Flood_Val'
                    colors = "Blues"
                    hover_label = 'Flood_Label'
                
                # Center
                lat_center = map_data.geometry.centroid.y.mean()
                lon_center = map_data.geometry.centroid.x.mean()

                # PLOT
                fig_map = px.choropleth_mapbox(
                    map_data,
                    geojson=map_data.geometry,
                    locations=map_data.index,
                    color=color_col,
                    color_continuous_scale=colors,
                    range_color=(0, 100),
                    mapbox_style="carto-positron",
                    center={"lat": lat_center, "lon": lon_center},
                    zoom=5.5,
                    opacity=0.6,
                    hover_name='District_Match',
                    hover_data={color_col: False, hover_label: True, 'Rain_Poss': True},
                    title=f"{map_view} - {selected_month} {week_of_month}"
                )
                fig_map.update_layout(height=600, margin={"r":0,"t":40,"l":0,"b":0})
                st.plotly_chart(fig_map, use_container_width=True)
            else:
                st.warning("No district data matched for this week.")

    st.markdown("---")

    # --- 4. DETAILS ---
    st.subheader("📊 District Risk Profile")
    sel_dist = st.selectbox("Select District for Details", district_list)
    
    if sel_dist:
        d_df = all_districts_data[sel_dist]
        d_df['Date'] = pd.to_datetime(d_df['Date'])
        
        heat_months, flood_months = calculate_risk_months(d_df)
        
        c1, c2 = st.columns(2)
        with c1:
            st.info(f"**🔥 Heat Risk Months:** {', '.join(heat_months) if heat_months else 'None'}")
        with c2:
            st.info(f"**⛈️ Flood Risk Months:** {', '.join(flood_months) if flood_months else 'None'}")
            
        curr_row = d_df[d_df['Week'] == week_of_year].iloc[0]
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Selected Week Status", curr_row['Risk_Alerts'])
        m2.metric("Flood Probability", f"{int(curr_row['Extreme_Rain_Prob_%'])}% ({get_risk_label(curr_row['Extreme_Rain_Prob_%'], 'flood')})")
        m3.metric("Heat Probability", f"{int(curr_row['Heat_Prob_%'])}% ({get_risk_label(curr_row['Heat_Prob_%'], 'heat')})")

if __name__ == "__main__":
    main()
