import streamlit as st
import pandas as pd
import geopandas as gpd
import plotly.express as px
import os
import glob
import warnings
import difflib  # Library for Smart Spelling Matches

# Suppress Warnings to keep dashboard clean
warnings.filterwarnings("ignore")

# ================= CONFIGURATION =================
PAGE_TITLE = "TRI Dashboard (IDS-DRR)"
AVAILABLE_YEARS = [2026]
SHAPEFILE_PATH = "DISTRICT_BOUNDARY.shp"

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
    div[data-testid="stMetricValue"] {
        font-size: 26px !important;
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
        # Clean filename to get nice state name
        state_name = os.path.basename(f).split("_DETAILED")[0].replace("_", " ")
        state_map[state_name] = f
    return state_map

@st.cache_data
def load_shapefile():
    """Loads map and cleans state names."""
    if os.path.exists(SHAPEFILE_PATH):
        gdf = gpd.read_file(SHAPEFILE_PATH)
        
        # Ensure Lat/Lon projection for Web Maps
        if gdf.crs != "EPSG:4326":
            gdf = gdf.to_crs(epsg=4326)
            
        # Standardize Names
        gdf['STATE_CLEAN'] = gdf['STATE'].str.upper().str.strip()
        gdf['DIST_CLEAN'] = gdf['District'].str.upper().str.strip()
        return gdf
    return None

@st.cache_data
def load_all_districts_data(file_path):
    """Reads the ENTIRE Excel file at once for speed."""
    try:
        return pd.read_excel(file_path, sheet_name=None)
    except:
        return None

def get_risk_label(prob, type='flood'):
    """Converts Probability % into Text Labels."""
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
    """Identifies which months have High Risk."""
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
        st.error("🚨 No data found. Please run the prediction script first.")
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
        # Calculate Week Number (Approx)
        month_idx = months.index(selected_month)
        week_of_year = (month_idx * 4) + int(week_of_month.split(" ")[1])
        if week_of_year > 52: week_of_year = 52

    with col3:
        map_view = st.radio("Visualize Risk Type:", ["Flood Risk", "Heat Risk"], horizontal=True)

    # --- 3. SMART MAP LOGIC (The Fix) ---
    gdf = load_shapefile()
    
    if gdf is not None:
        # === AUTO-MATCH STATE NAME ===
        # This finds the closest state name in the map, even if spelling is wrong
        map_states = gdf['STATE_CLEAN'].unique()
        clean_selected = selected_state.upper().strip()
        
        # Use fuzzy matching (cutoff=0.6 means 60% similarity required)
        matches = difflib.get_close_matches(clean_selected, map_states, n=1, cutoff=0.6)
        
        if matches:
            matched_state = matches[0]
            if matched_state != clean_selected:
                st.success(f"🗺️ Auto-Matched Map: '{selected_state}' ➡️ '{matched_state}'")
            
            # Filter Map for the matched state
            state_gdf = gdf[gdf['STATE_CLEAN'] == matched_state].copy()
        else:
            st.error(f"❌ Could not find a map layer for '{selected_state}'.")
            st.write("Available States in Map:", map_states)
            state_gdf = pd.DataFrame() # Empty frame

        if not state_gdf.empty:
            week_risk_data = []
            
            # Prepare Risk Data
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
                
                # === SAFE MERGE & FILLNA (Prevents Crashes) ===
                # 1. Merge
                map_data = state_gdf.merge(risk_df, left_on='DIST_CLEAN', right_on='District_Match', how='left')
                
                # 2. Force GeoDataFrame
                map_data = gpd.GeoDataFrame(map_data, geometry='geometry')
                
                # 3. Fill only data columns (Not geometry)
                cols_to_fill = ['Heat_Val', 'Flood_Val', 'Heat_Label', 'Flood_Label', 'Rain_Poss']
                for col in cols_to_fill:
                    if col in map_data.columns:
                        if 'Val' in col:
                            map_data[col] = map_data[col].fillna(0)
                        else:
                            map_data[col] = map_data[col].fillna("No Data")
                
                # Determine Colors
                if map_view == "Heat Risk":
                    color_col = 'Heat_Val'
                    colors = "Reds"
                    hover_label = 'Heat_Label'
                else:
                    color_col = 'Flood_Val'
                    colors = "Blues"
                    hover_label = 'Flood_Label'
                
                # Calculate Center
                lat_center = map_data.geometry.centroid.y.mean()
                lon_center = map_data.geometry.centroid.x.mean()

                # PLOT MAP
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
                    hover_data={
                        color_col: False,
                        hover_label: True,
                        'Rain_Poss': True
                    },
                    title=f"{map_view} - {selected_month} {week_of_month}"
                )
                fig_map.update_layout(height=600, margin={"r":0,"t":40,"l":0,"b":0})
                st.plotly_chart(fig_map, use_container_width=True)
            else:
                st.warning(f"No prediction data matched the map districts for {selected_state}.")

    st.markdown("---")

    # --- 4. DISTRICT RISK PROFILE ---
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

    # ================= 5. DEBUGGING TOOL =================
    with st.expander("🛠️ Map Troubleshooter (Click if map is empty)"):
        st.write(f"**Selected Excel State:** {selected_state}")
        
        if gdf is not None:
            # Check District Matching
            st.write("**District Mismatch Check:**")
            excel_districts = set([k.upper().strip() for k in all_districts_data.keys()])
            
            # Use the Matched State from Logic
            if 'matched_state' in locals():
                map_districts = set(gdf[gdf['STATE_CLEAN'] == matched_state]['DIST_CLEAN'].unique())
                common = excel_districts.intersection(map_districts)
                missing = excel_districts - map_districts
                
                st.write(f"✅ Matched Districts: {len(common)}")
                if missing:
                    st.warning(f"⚠️ {len(missing)} districts are in Excel but NOT in Map:")
                    st.code(list(missing))
            else:
                st.write("Could not check districts because State Name did not match.")

if __name__ == "__main__":
    main()
