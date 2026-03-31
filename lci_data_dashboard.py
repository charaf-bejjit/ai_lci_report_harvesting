import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="LCI Data Exploration", layout="wide")

# =========================
# TITLE
# =========================

st.title("AI-based LCI Data Extraction Dashboard")

st.markdown("""
This interface presents key statistics extracted from company reports 
for Cu and Ni mining and refining activities.
""")

# =========================
# DATA (TES DONNÉES)
# =========================

cu_data = {
    "Economics": {"table": 7637, "text": 1714, "graph": 494},
    "Emissions": {"table": 7469, "text": 1562, "graph": 1647},
    "Energy": {"table": 6724, "text": 1049, "graph": 510},
    "Geology": {"table": 9792, "text": 1300, "graph": 103},
    "Land": {"table": 1306, "text": 986, "graph": 107},
    "Other": {"table": 1146, "text": 987, "graph": 165},
    "Production": {"table": 8012, "text": 3453, "graph": 776},
    "Waste": {"table": 5862, "text": 1196, "graph": 377},
    "Water": {"table": 8249, "text": 2002, "graph": 619}
}

ni_data = {
    "Economics": {"table": 3743, "text": 1232, "graph": 172},
    "Emissions": {"table": 2965, "text": 799, "graph": 438},
    "Energy": {"table": 3006, "text": 945, "graph": 270},
    "Geology": {"table": 3053, "text": 426, "graph": 9},
    "Land": {"table": 1488, "text": 997, "graph": 61},
    "Other": {"table": 666, "text": 397, "graph": 46},
    "Production": {"table": 3051, "text": 1880, "graph": 450},
    "Waste": {"table": 1927, "text": 495, "graph": 267},
    "Water": {"table": 5781, "text": 1177, "graph": 724}
}

categories = [
    "Production", "Geology", "Economics", "Emissions",
    "Water", "Energy", "Waste", "Land", "Other"
]

data = []

for cat in categories:
    table = cu_data[cat]["table"] + ni_data[cat]["table"]
    text = cu_data[cat]["text"] + ni_data[cat]["text"]
    graph = cu_data[cat]["graph"] + ni_data[cat]["graph"]
    total = table + text + graph
    data.append((cat, table, text, graph, total))

data_sorted = sorted(data, key=lambda x: x[4], reverse=True)

categories_sorted = [x[0] for x in data_sorted]
table_vals = [x[1] for x in data_sorted]
text_vals = [x[2] for x in data_sorted]
graph_vals = [x[3] for x in data_sorted]

# =========================
# GRAPH
# =========================

fig = go.Figure()

fig.add_bar(x=categories_sorted, y=table_vals, name="Table")
fig.add_bar(x=categories_sorted, y=text_vals, name="Text")
fig.add_bar(x=categories_sorted, y=graph_vals, name="Graph")

fig.update_layout(
    barmode='stack',
    template="simple_white"
)

st.plotly_chart(fig, use_container_width=True)

# =========================
# SUMMARY
# =========================

st.subheader("Key insights")

st.write("""
- Water and Production categories contain the largest number of extracted metrics  
- Tables represent the dominant source of extracted data  
- Graph-based extraction remains more limited compared to text and tables  
""")