import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

st.set_page_config(page_title="LCI Dashboard", layout="wide")

st.title("AI-based LCI Data Extraction Dashboard")

st.markdown(
    """
This dashboard presents the main statistics associated with the Cu and Ni case studies.
It first summarizes report screening and extraction results, then focuses on the manual verification
performed for the copper case study, and finally reproduces the energy-intensity visualizations used in the article.
"""
)

PLOTLY_CONFIG = {
    "editable": True,
    "displaylogo": False,
    "scrollZoom": False
}

# =========================================================
# DATA — SCREENING
# =========================================================

screening = {
    "Copper": {
        "total_reports": 354,
        "failed": 17,
        "auto_go": 218,
        "auto_maybe": 69,
        "auto_nogo": 50,
        "review_set": 287,      # GO + MAYBE
        "retained": 129,        # final GO
        "review_excluded": 158, # from review set
        "final_excluded": 225   # 354 - 129
    },
    "Nickel": {
        "total_reports": 342,
        "failed": 6,
        "auto_go": 106,
        "auto_maybe": 55,
        "auto_nogo": 175,
        "review_set": 161,      # GO + MAYBE
        "retained": 46,         # final GO
        "review_excluded": 115, # from review set
        "final_excluded": 296   # 342 - 46
    }
}

# =========================================================
# DATA — EXTRACTION (ARTICLE TOTALS + Cu stats)
# =========================================================

# Combined totals used in article
combined_source = {
    "Table": 90749,
    "Text": 23425,
    "Graph": 7541  # graph + image + diagram
}

combined_category = {
    "Water": 18552,
    "Production": 17156,
    "Emissions": 14880,
    "Geology": 14683,
    "Economics": 14326,
    "Energy": 12504,
    "Waste": 10124,
    "Land": 4945,
    "Other": 3242
}

# Copper stats you provided
cu_source = {
    "Table": 55822,
    "Text": 14833,
    "Graph": 5002 + 24 + 1
}

cu_category = {
    "Production": 13054,
    "Geology": 11374,
    "Economics": 10574,
    "Emissions": 10505,
    "Water": 10071,
    "Energy": 8122,
    "Waste": 7311,
    "Land": 2404,
    "Other": 2262
}

# Nickel derived from the article-level combined totals minus Cu
ni_source = {
    "Table": combined_source["Table"] - cu_source["Table"],
    "Text": combined_source["Text"] - cu_source["Text"],
    "Graph": combined_source["Graph"] - cu_source["Graph"]
}

ni_category = {
    k: combined_category[k] - cu_category[k]
    for k in cu_category.keys()
}

# =========================================================
# DATA — COPPER VALIDATION
# =========================================================

validation_global = {
    "Correct": 4479,
    "Partial": 962,
    "Incorrect": 49
}

validation_source = {
    "Table": {"Correct": 3536, "Partial": 634, "Incorrect": 7},
    "Text": {"Correct": 505, "Partial": 228, "Incorrect": 0},
    "Graph": {"Correct": 438, "Partial": 98, "Incorrect": 42}
}

validation_category = {
    "Production": {"Correct": 673, "Partial": 139, "Incorrect": 0},
    "Emissions": {"Correct": 852, "Partial": 64, "Incorrect": 32},
    "Economics": {"Correct": 211, "Partial": 428, "Incorrect": 7},
    "Energy": {"Correct": 568, "Partial": 44, "Incorrect": 0},
    "Water": {"Correct": 743, "Partial": 202, "Incorrect": 0},
    "Waste": {"Correct": 716, "Partial": 7, "Incorrect": 0},
    "Land": {"Correct": 136, "Partial": 36, "Incorrect": 0},
    "Other": {"Correct": 100, "Partial": 2, "Incorrect": 0},
    "Geology": {"Correct": 479, "Partial": 40, "Incorrect": 10}
}

# =========================================================
# HELPER FUNCTIONS
# =========================================================

def donut_chart(title, labels, values):
    fig = go.Figure(
        data=[go.Pie(labels=labels, values=values, hole=0.5)]
    )
    fig.update_layout(title=title, margin=dict(t=60, b=20, l=20, r=20))
    return fig

def stacked_bar(title, x_labels, correct_vals, partial_vals, incorrect_vals, y_title="Count"):
    fig = go.Figure()
    fig.add_bar(name="Correct", x=x_labels, y=correct_vals)
    fig.add_bar(name="Partial", x=x_labels, y=partial_vals)
    fig.add_bar(name="Incorrect", x=x_labels, y=incorrect_vals)
    fig.update_layout(
        title=title,
        barmode="stack",
        yaxis_title=y_title,
        xaxis_title="",
        margin=dict(t=60, b=20, l=20, r=20)
    )
    return fig

def screening_sankey(case_name, d):

    labels = ["GO", "NO-GO", "MAYBE", "Retained", "Excluded"]

    # POSITIONS FORCÉES (clé)
    x = [0.0, 0.0, 0.0, 1.0, 1.0]
    y = [0.0, 0.5, 0.9, 0.2, 0.75]  # GO haut, NO-GO milieu, MAYBE bas

    COLORS = {
        "go": "#2E7D32",
        "nogo": "#C62828",
        "maybe": "#F57C00",
        "retained": "#66BB6A",
        "excluded": "#EF5350",
        "flow": "rgba(120,120,120,0.35)"
    }

    review_total = d["auto_go"] + d["auto_maybe"]

    retained = d["retained"]
    excluded = d["review_excluded"]

    go_to_retained = d["auto_go"] * retained / review_total
    go_to_excluded = d["auto_go"] * excluded / review_total

    maybe_to_retained = d["auto_maybe"] * retained / review_total
    maybe_to_excluded = d["auto_maybe"] * excluded / review_total

    fig = go.Figure(go.Sankey(
        arrangement="snap",  # 🔥 PAS DE TRI
        node=dict(
            label=labels,
            x=x,
            y=y,
            pad=40,
            thickness=30,
            color=[
                COLORS["go"],
                COLORS["nogo"],
                COLORS["maybe"],
                COLORS["retained"],
                COLORS["excluded"]
            ]
        ),
        link=dict(
            source=[0, 0, 2, 2, 1],
            target=[3, 4, 3, 4, 4],
            value=[
                go_to_retained,
                go_to_excluded,
                maybe_to_retained,
                maybe_to_excluded,
                d["auto_nogo"]
            ],
            color=COLORS["flow"]
        )
    ))

    fig.update_layout(
        title=f"{case_name} — screening and validation flow",
        dragmode="pan"  # 🔥 INTERACTIF (déplacement)
    )

    return fig

def format_site(name):
    return "<br>".join(str(name).split())

# =========================================================
# 1. GENERAL SCREENING RESULTS
# =========================================================

st.header("1. Screening and human validation")

st.markdown(
    """
This section summarizes the report-selection workflow for the Cu and Ni case studies,
including automated screening decisions, final outcomes after expert review,
and report-flow diagrams.
"""
)
# 👇 LÉGENDE ICI (AVANT LES SANKEY)
col1, col2 = st.columns(2)

with col1:
    st.plotly_chart(
        donut_chart(
            "Copper — automatic screening",
            ["GO", "MAYBE", "NO-GO", "Failed"],
            [
                screening["Copper"]["auto_go"],
                screening["Copper"]["auto_maybe"],
                screening["Copper"]["auto_nogo"],
                screening["Copper"]["failed"]
            ]
        ),
        use_container_width=True
    )

with col2:
    st.plotly_chart(
        donut_chart(
            "Nickel — automatic screening",
            ["GO", "MAYBE", "NO-GO", "Failed"],
            [
                screening["Nickel"]["auto_go"],
                screening["Nickel"]["auto_maybe"],
                screening["Nickel"]["auto_nogo"],
                screening["Nickel"]["failed"]
            ]
        ),
        use_container_width=True
    )

col1, col2 = st.columns(2)

with col1:
    st.plotly_chart(
        donut_chart(
            "Copper — final outcome",
            ["Retained for extraction", "Excluded"],
            [
                screening["Copper"]["retained"],
                screening["Copper"]["final_excluded"]
            ]
        ),
        use_container_width=True
    )

with col2:
    st.plotly_chart(
        donut_chart(
            "Nickel — final outcome",
            ["Retained for extraction", "Excluded"],
            [
                screening["Nickel"]["retained"],
                screening["Nickel"]["final_excluded"]
            ]
        ),
        use_container_width=True
    )

st.markdown("""
<div style="
display:flex;
justify-content:center;
gap:40px;
font-size:16px;
margin-bottom:10px;
">
<span style="color:#2E7D32;">● GO</span>
<span style="color:#C62828;">● NO-GO</span>
<span style="color:#F57C00;">● MAYBE</span>
<span style="color:#66BB6A;">● Retained</span>
<span style="color:#EF5350;">● Excluded</span>
</div>
""", unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    st.plotly_chart(
        screening_sankey("Copper", screening["Copper"]),
        use_container_width=True,
        config=PLOTLY_CONFIG
    )

with col2:
    st.plotly_chart(
        screening_sankey("Nickel", screening["Nickel"]),
        use_container_width=True,
        config=PLOTLY_CONFIG
    )

# =========================================================
# 2. EXTRACTED DATA — ARTICLE GRAPH + Cu/Ni COMPARISON
# =========================================================

st.header("2. Extracted data overview")

st.markdown(
    """
The first graph reproduces the article-level distribution of extracted metrics
for the combined Cu and Ni corpus. The following charts then compare Cu and Ni separately.
"""
)

# Combined article graph
order = ["Water", "Production", "Emissions", "Geology", "Economics", "Energy", "Waste", "Land", "Other"]
combined_df = pd.DataFrame({
    "Category": order,
    "Count": [combined_category[k] for k in order]
})

fig_combined_bar = go.Figure(
    data=[go.Bar(x=combined_df["Category"], y=combined_df["Count"])]
)
fig_combined_bar.update_layout(
    title="Combined extracted metrics by category (175 reports)",
    xaxis_title="Metrics category",
    yaxis_title="Number of extracted metrics",
    margin=dict(t=60, b=20, l=20, r=20)
)

st.plotly_chart(fig_combined_bar, use_container_width=True, config=PLOTLY_CONFIG)

fig_combined_pie = donut_chart(
    "Combined source-type distribution",
    list(combined_source.keys()),
    list(combined_source.values())
)
st.plotly_chart(fig_combined_pie, use_container_width=True, config=PLOTLY_CONFIG)

col1, col2 = st.columns(2)

with col1:
    st.plotly_chart(
        donut_chart(
            "Copper — source-type distribution",
            list(cu_source.keys()),
            list(cu_source.values())
        ),
        use_container_width=True,
        config=PLOTLY_CONFIG
    )

with col2:
    st.plotly_chart(
        donut_chart(
            "Nickel — source-type distribution",
            list(ni_source.keys()),
            list(ni_source.values())
        ),
        use_container_width=True,
        config=PLOTLY_CONFIG
    )

# =========================================================
# 3. COPPER VALIDATION RESULTS
# =========================================================

st.header("3. Copper case study — manual verification")

st.markdown(
    """
Manual verification was conducted on a subset of the copper extraction results.
The charts below summarize overall validation performance, validation by source type,
and validation by category.
"""
)

fig_val_global = donut_chart(
    "Copper — overall validation",
    list(validation_global.keys()),
    list(validation_global.values())
)
st.plotly_chart(fig_val_global, use_container_width=True, config=PLOTLY_CONFIG)

fig_val_source = stacked_bar(
    "Copper — validation by source type",
    list(validation_source.keys()),
    [validation_source[k]["Correct"] for k in validation_source.keys()],
    [validation_source[k]["Partial"] for k in validation_source.keys()],
    [validation_source[k]["Incorrect"] for k in validation_source.keys()]
)
st.plotly_chart(fig_val_source, use_container_width=True, config=PLOTLY_CONFIG)

val_cat_order = ["Production", "Emissions", "Economics", "Energy", "Water", "Waste", "Land", "Other", "Geology"]
fig_val_cat = stacked_bar(
    "Copper — validation by category",
    val_cat_order,
    [validation_category[k]["Correct"] for k in val_cat_order],
    [validation_category[k]["Partial"] for k in val_cat_order],
    [validation_category[k]["Incorrect"] for k in val_cat_order]
)
st.plotly_chart(fig_val_cat, use_container_width=True, config=PLOTLY_CONFIG)

st.markdown(
    """
**Note:** “Partial” corresponds to cases where the numerical value was correctly extracted
but could not be unambiguously associated with a specific production site or local operational context.
"""
)

# =========================================================
# 4. COPPER ENERGY INTENSITY FIGURES
# =========================================================

st.header("4. Copper energy intensity figures")

st.markdown(
    """
The dashboard generates:
- the ascending curve for **Cu concentrate**
- the ascending curve for **Cu cathode**
- a combined **bubble plot** for both product types
"""
)

# === Local path exactly as requested ===
file_path = r"C:\Users\bejjit\Downloads\20260225_Cu_Intensity&Prod_Results_v3 (1).xlsx"
df = pd.read_excel(file_path)

# Clean
df["Production site"] = df["Production site"].astype(str).str.strip()
df["Main product"] = df["Main product"].astype(str).str.strip()
df["Total energy consumption"] = df["Total energy consumption"].astype(str).str.strip()

df = df[df["Total energy consumption"].isin([
    "Electricity consumption",
    "Fuel consumption",
    "Electricity and fuel consumption"
])].copy()

# Convert production to '000 tonnes
df["Annual Cu production (t)"] = df["Annual Cu production (t)"] / 1000

# Pivot
pivot = df.pivot_table(
    index=["Production site", "Main product", "Annual Cu production (t)"],
    columns="Total energy consumption",
    values="Energy intensity (GJ/t Cu)",
    aggfunc="sum",
    fill_value=0
).reset_index()

for col in [
    "Electricity consumption",
    "Fuel consumption",
    "Electricity and fuel consumption"
]:
    if col not in pivot.columns:
        pivot[col] = 0

pivot["Total intensity"] = (
    pivot["Electricity consumption"]
    + pivot["Fuel consumption"]
    + pivot["Electricity and fuel consumption"]
)

colors = {
    "electricity": "#A9CBE8",
    "combined": "#4F81BD",
    "fuel": "#0B3C6D"
}

def build_curve(data, title):
    d = data.sort_values("Total intensity", ascending=True).copy()

    d["x_start"] = d["Annual Cu production (t)"].cumsum() - d["Annual Cu production (t)"]
    d["x_center"] = d["x_start"] + d["Annual Cu production (t)"] / 2

    total_width = d["Annual Cu production (t)"].sum()

    fig = go.Figure()

    fig.add_bar(
        x=d["x_center"],
        y=d["Electricity consumption"],
        width=d["Annual Cu production (t)"],
        name="Electricity",
        marker_color=colors["electricity"]
    )

    fig.add_bar(
        x=d["x_center"],
        y=d["Electricity and fuel consumption"],
        width=d["Annual Cu production (t)"],
        name="Fuel & Electricity",
        marker_color=colors["combined"]
    )

    fig.add_bar(
        x=d["x_center"],
        y=d["Fuel consumption"],
        width=d["Annual Cu production (t)"],
        name="Fuel",
        marker_color=colors["fuel"]
    )

    for i, row in d.iterrows():
        fig.add_annotation(
            x=row["x_center"],
            y=row["Total intensity"],
            text=format_site(row["Production site"]),
            showarrow=True,
            arrowhead=2,
            ax=0,
            ay=-60 if i % 2 == 0 else -100,
            font=dict(size=14),
            align="center"
        )

    if total_width < 500:
        dtick = 100
    elif total_width < 1000:
        dtick = 100
    elif total_width < 3000:
        dtick = 500
    else:
        dtick = 500

    fig.update_layout(
        barmode="stack",
        template="plotly_white",
        bargap=0,
        title=title,
        dragmode="pan",
        xaxis=dict(
            title="Annual Cu production ('000 tonnes)",
            range=[0, total_width],
            tickmode="linear",
            tick0=0,
            dtick=dtick,
            showgrid=True,
            gridcolor="lightgrey"
        ),
        yaxis=dict(title="Energy intensity (GJ/t Cu)"),
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1.0,
            xanchor="left",
            x=0.01,
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="rgba(0,0,0,0.1)",
            borderwidth=1
        ),
        margin=dict(t=60, b=20, l=20, r=20)
    )
    return fig

conc = pivot[pivot["Main product"] == "Cu concentrate"].copy()
cath = pivot[pivot["Main product"] == "Cu cathode"].copy()

col1, col2 = st.columns(2)

with col1:
    if not conc.empty:
        st.plotly_chart(
            build_curve(conc, "Cu concentrate — ascending"),
            use_container_width=True,
            config=PLOTLY_CONFIG
        )
    else:
        st.info("No Cu concentrate data found in the file.")

with col2:
    if not cath.empty:
        st.plotly_chart(
            build_curve(cath, "Cu cathode — ascending"),
            use_container_width=True,
            config=PLOTLY_CONFIG
        )
    else:
        st.info("No Cu cathode data found in the file.")

st.markdown(
    """
ℹ️ **Note:** These figures are interactive. Site labels in the stacked charts can be manually repositioned for improved readability if overlap occurs.
"""
)
