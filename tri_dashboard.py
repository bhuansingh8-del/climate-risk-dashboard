import streamlit as st
import pandas as pd
import geopandas as gpd
import plotly.express as px
import os
import glob
import warnings

# Suppress Warnings
warnings.filterwarnings("ignore")

# ================= CONFIGURATION =================
PAGE_TITLE = "TRI Dashboard (IDS-DRR)"
AVAILABLE_YEARS = [2026]

# ⚠️ IMPORTANT: If your file on GitHub is named "DISTRICT_BOUNDARY_CLEAN.shp", change this line!
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
        font-size: 22px !important;
        font-weight: bold !important;
        padding: 15px 30px;
        border: 2px solid #e0e0e0;
        border-radius: 10px;
        margin-right: 15px;
        background-color: white;
        color: black;
    }
    div[role="radiogroup"] {
        display: flex;
        flex-direction: row;
        gap: 20px;
    }
    div[data-testid="stMetricValue"] {
        font-size: 28px !important;
    }
</style>
""", unsafe_allow_html=True)

# ================= DATA FUNCTIONS =================

@st.cache_data
def load_state_files():
    files = glob.glob("*_DETAILED_PREDICTIONS_*.xlsx")
    state_map = {}
    for f in files:
        # Extract state name: "ASSAM_DETAILED_PREDICTIONS..." -> "ASSAM"
        state_name = os.path.basename(f).split("_DETAILED")[0].replace("_", " ")
        state_map[state_name] = f
    return state_map

@st.cache_data
def load_shapefile():
    if os.path.exists(SHAPEFILE_PATH):
        # Read file
        gdf = gpd.read_file(SHAPEFILE_PATH)
        
        # Force conversion to Lat/Lon (Standard for Web Maps)
        if gdf.crs != "EPSG:4326":
            gdf = gdf.to_crs(epsg=4326)
            
        # Standardize Names
        gdf['STATE_CLEAN'] = gdf['STATE'].str.upper().str.strip()
        gdf['DIST_CLEAN'] = gdf['District'].str.upper().str.strip()
        
        # === SPELLING FIXER (Fixes Maharashtra, Chhattisgarh, etc.) ===
        state_fixes = {
            'CHHATISGARH': 'CHHATTISGARH',   # Fixes missing 'T'
            'CHATTISGARH': 'CHHATTISGARH',
            'ORISSA': 'ODISHA',
            'UTTARANCHAL': 'UTTARAKHAND',
            'JAMMU AND KASHMIR': 'JAMMU & KASHMIR',
            'PONDICHERRY': 'PUDUCHERRY',
            'MAHARASTRA': 'MAHARASHTRA'      # Fixes missing 'H'
        }
        gdf['STATE_CLEAN'] = gdf['STATE_CLEAN'].replace(state_fixes)
        
        return gdf
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
        st.error("🚨 No data found.")
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

    # --- 3. MAP LOGIC ---
    gdf = load_shapefile()
    
    if gdf is not None:
        # Filter for selected state (using flexible matching)
        state_gdf = gdf[gdf['STATE_CLEAN'].str.contains(selected_state.split()[0], na=False)].copy()
        
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
                
                # === SAFE MERGE ===
                map_data = state_gdf.merge(risk_df, left_on='DIST_CLEAN', right_on='District_Match', how='left')
                map_data = gpd.GeoDataFrame(map_data, geometry='geometry')
                
                # === SAFE FILLNA (Prevents crash) ===
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
                st.warning(f"No prediction data matches the map for {selected_state}.")

    st.markdown("---")

    # --- 4. RISK SEASON ANALYSIS ---
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
    # This helps you fix maps if they are still grey
    with st.expander("🛠️ Map Troubleshooter (Click if map is empty)"):
        st.write(f"**Selected State:** {selected_state}")
        
        if gdf is not None:
            # Check if State exists
            all_map_states = gdf['STATE_CLEAN'].unique()
            # Try partial match
            match = [s for s in all_map_states if selected_state.split()[0] in s]
            
            if match:
                st.success(f"✅ Found State in Map as: '{match[0]}'")
            else:
                st.error(f"❌ Could not find '{selected_state}' in map.")
                st.write("Available States:", all_map_states)
            
            # Check District Matching
            st.write("**District Mismatch Check:**")
            excel_districts = set([k.upper().strip() for k in all_districts_data.keys()])
            
            if match:
                map_districts = set(gdf[gdf['STATE_CLEAN'] == match[0]]['DIST_CLEAN'].unique())
                missing = excel_districts - map_districts
                
                if missing:
                    st.warning(f"⚠️ {len(missing)} districts are in Excel but NOT in Map (Name mismatch):")
                    st.write(list(missing))
                else:
                    st.success("✅ All districts match perfectly!")

if __name__ == "__main__":
    main()
