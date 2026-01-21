import streamlit as st
import pandas as pd
import geopandas as gpd
import plotly.express as px
import os
import glob
import warnings
import difflib

# 1. Suppress warnings
warnings.filterwarnings("ignore")
os.environ["PYTHONWARNINGS"] = "ignore"

# ================= CONFIGURATION =================
PAGE_TITLE = "TRI Dashboard (IDS-DRR)"
st.set_page_config(page_title=PAGE_TITLE, layout="wide")

# ================= CUSTOM CSS =================
st.markdown("""
<style>
    .stApp { background-color: white; color: black; }
    div[role="radiogroup"] > label {
        font-size: 18px !important;
        font-weight: 600 !important;
        padding: 8px 20px;
        border: 2px solid #eee;
        border-radius: 8px;
        background-color: #f9f9f9;
        color: #333;
    }
    div[data-testid="stMetricValue"] { font-size: 24px; }
</style>
""", unsafe_allow_html=True)

# ================= FUNCTIONS =================

@st.cache_data
def load_state_files():
    """Finds all prediction Excel files."""
    files = glob.glob("*_DETAILED_PREDICTIONS_*.xlsx")
    state_map = {}
    for f in files:
        state_name = os.path.basename(f).split("_DETAILED")[0].replace("_", " ")
        state_map[state_name] = f
    return state_map

@st.cache_data
def load_shapefile():
    """Auto-detects .shp file."""
    shp_files = glob.glob("*.shp")
    if not shp_files:
        return None
    try:
        gdf = gpd.read_file(shp_files[0])
        if gdf.crs != "EPSG:4326":
            gdf = gdf.to_crs(epsg=4326)
        gdf['STATE_CLEAN'] = gdf['STATE'].str.upper().str.strip()
        gdf['DIST_CLEAN'] = gdf['District'].str.upper().str.strip()
        return gdf
    except Exception as e:
        st.error(f"Shapefile Error: {e}")
        return None

@st.cache_data
def load_all_districts_data(file_path):
    try:
        return pd.read_excel(file_path, sheet_name=None)
    except:
        return None

def get_risk_label(prob, type='flood'):
    """
    Returns text label based on probability %.
    Note: Ideally, 'prob' should be the probability of RAINFALL > 64.5mm (Heavy Rain).
    """
    if prob < 30: 
        return "Low Risk (Normal)"
    elif prob < 60: 
        return "Moderate Risk (Watch)"
    elif prob < 85: 
        return "High Risk (Alert)"
    else: 
        return "Critical (Warning)"

def calculate_risk_months(df):
    df['Month'] = df['Date'].dt.month_name()
    # Using 50% probability as the cutoff for listing a month as "Risky"
    high_heat = df[df['Heat_Prob_%'] > 50]['Month'].unique()
    high_flood = df[df['Extreme_Rain_Prob_%'] > 50]['Month'].unique()
    return list(high_heat), list(high_flood)

# ================= MAIN DASHBOARD =================

def main():
    st.title(f"🌍 {PAGE_TITLE}")

    # --- 1. SIDEBAR SETUP ---
    available_states = load_state_files()
    if not available_states:
        st.error("🚨 No data found. Please ensure '_DETAILED_PREDICTIONS_' Excel files are in the folder.")
        st.stop()

    st.sidebar.header("📍 Settings")
    selected_state = st.sidebar.selectbox("Select State", list(available_states.keys()))
    state_file_path = available_states[selected_state]

    with st.spinner("Loading Data..."):
        all_districts_data = load_all_districts_data(state_file_path)
    
    if not all_districts_data:
        st.error("Could not load Excel data.")
        st.stop()
        
    district_list = list(all_districts_data.keys())

    # --- 2. CONTROLS ---
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        months = ['January', 'February', 'March', 'April', 'May', 'June', 
                  'July', 'August', 'September', 'October', 'November', 'December']
        selected_month = st.selectbox("📅 Month", months)
        
    with col2:
        week_of_month = st.selectbox("📆 Week", ["Week 1", "Week 2", "Week 3", "Week 4"])
        month_idx = months.index(selected_month)
        week_of_year = (month_idx * 4) + int(week_of_month.split(" ")[1])
        if week_of_year > 52: week_of_year = 52

    with col3:
        map_view = st.radio("Visualize Risk Type:", ["Flood Risk (Heavy Rain)", "Heat Risk (Wet Bulb)"], horizontal=True)

    st.markdown("---")

    # --- 3. MAP VISUALIZATION ---
    gdf = load_shapefile()
    
    if gdf is not None:
        # Match State
        map_states = gdf['STATE_CLEAN'].unique()
        clean_selected = selected_state.upper().strip()
        matches = difflib.get_close_matches(clean_selected, map_states, n=1, cutoff=0.6)
        
        if matches:
            matched_state = matches[0]
            state_gdf = gdf[gdf['STATE_CLEAN'] == matched_state].copy()
            
            # Prepare Data for Map
            week_risk_data = []
            for dist_name, df in all_districts_data.items():
                # Filter for selected week
                row = df[df['Week'] == week_of_year]
                if not row.empty:
                    r = row.iloc[0]
                    heat_val = r.get('Heat_Prob_%', 0)
                    flood_val = r.get('Extreme_Rain_Prob_%', 0)
                    
                    week_risk_data.append({
                        'District_Match': dist_name.upper().strip(),
                        'Heat_Val': heat_val,
                        'Flood_Val': flood_val,
                        'Heat_Label': get_risk_label(heat_val, 'heat'),
                        'Flood_Label': get_risk_label(flood_val, 'flood')
                    })

            if week_risk_data:
                risk_df = pd.DataFrame(week_risk_data)
                
                # Merge Data
                map_data = state_gdf.merge(risk_df, left_on='DIST_CLEAN', right_on='District_Match', how='left')
                map_data = gpd.GeoDataFrame(map_data, geometry='geometry')
                
                # Fill Missing
                map_data['Heat_Val'] = map_data['Heat_Val'].fillna(0)
                map_data['Flood_Val'] = map_data['Flood_Val'].fillna(0)
                map_data['Heat_Label'] = map_data['Heat_Label'].fillna("No Data")
                map_data['Flood_Label'] = map_data['Flood_Label'].fillna("No Data")

                # Configure Plot based on Selection
                if "Heat" in map_view:
                    color_col = 'Heat_Val'
                    # Red scale for Heat
                    colors = "Reds"
                    hover_lbl = 'Heat_Label'
                else:
                    color_col = 'Flood_Val'
                    # Blue scale for Flood
                    colors = "Blues"
                    hover_lbl = 'Flood_Label'

                # --- DEBUG SECTION ---
                with st.expander("🔍 Debug: Inspect Raw Data Range"):
                    min_val = risk_df[color_col].min()
                    max_val = risk_df[color_col].max()
                    st.write(f"**Min Probability in Data:** {min_val}%")
                    st.write(f"**Max Probability in Data:** {max_val}%")
                    if min_val == 100 and max_val == 100:
                        st.error("⚠️ All districts have 100% probability. Please check your Excel generation logic. The model might be too sensitive.")

                # PLOT
                lat_center = map_data.geometry.centroid.y.mean()
                lon_center = map_data.geometry.centroid.x.mean()

                fig_map = px.choropleth_mapbox(
                    map_data,
                    geojson=map_data.geometry,
                    locations=map_data.index,
                    color=color_col,
                    color_continuous_scale=colors,
                    # FIXED RANGE: This ensures 30% looks light and 100% looks dark
                    range_color=(0, 100), 
                    mapbox_style="carto-positron",
                    center={"lat": lat_center, "lon": lon_center},
                    zoom=5.5,
                    opacity=0.6,
                    hover_name='District_Match',
                    hover_data={color_col: True, hover_lbl: True, "DIST_CLEAN": False},
                    title=f"{map_view} Prediction - {selected_month}"
                )
                fig_map.update_layout(height=600, margin={"r":0,"t":40,"l":0,"b":0})
                st.plotly_chart(fig_map, use_container_width=True)
            else:
                st.warning("No data found for this week.")
        else:
            st.error(f"Could not match state '{selected_state}' to Map.")

    # --- 4. DETAILS PANE ---
    if district_list:
        st.subheader("📊 District Details")
        sel_dist = st.selectbox("Select District", district_list)
        
        if sel_dist:
            d_df = all_districts_data[sel_dist]
            d_df['Date'] = pd.to_datetime(d_df['Date'])
            
            # Filter for current week
            curr_row = d_df[d_df['Week'] == week_of_year]
            
            if not curr_row.empty:
                curr_row = curr_row.iloc[0]
                h_prob = curr_row.get('Heat_Prob_%', 0)
                f_prob = curr_row.get('Extreme_Rain_Prob_%', 0)
                
                m1, m2 = st.columns(2)
                m1.metric("Flood Risk Probability", f"{int(f_prob)}%", get_risk_label(f_prob, 'flood'))
                m2.metric("Heat Risk Probability", f"{int(h_prob)}%", get_risk_label(h_prob, 'heat'))
            else:
                st.info("No data for this specific week.")

if __name__ == "__main__":
    main()
