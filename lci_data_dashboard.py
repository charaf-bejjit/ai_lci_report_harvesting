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
    labels = [
        f"{case_name} automatic NO-GO",
        f"{case_name} failed",
        f"{case_name} review set (GO + MAYBE)",
        f"{case_name} retained",
        f"{case_name} excluded"
    ]

    fig = go.Figure(
        data=[go.Sankey(
            node=dict(label=labels, pad=20, thickness=20),
            link=dict(
                source=[0, 1, 2, 2],
                target=[4, 4, 3, 4],
                value=[
                    d["auto_nogo"],
                    d["failed"],
                    d["retained"],
                    d["review_excluded"]
                ]
            )
        )]
    )
    fig.update_layout(
        title=f"{case_name} — screening and validation flow",
        margin=dict(t=60, b=20, l=20, r=20)
    )
    return fig

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

col1, col2 = st.columns(2)

with col1:
    st.plotly_chart(screening_sankey("Copper", screening["Copper"]), use_container_width=True)

with col2:
    st.plotly_chart(screening_sankey("Nickel", screening["Nickel"]), use_container_width=True)

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

st.plotly_chart(fig_combined_bar, use_container_width=True)

fig_combined_pie = donut_chart(
    "Combined source-type distribution",
    list(combined_source.keys()),
    list(combined_source.values())
)
st.plotly_chart(fig_combined_pie, use_container_width=True)

col1, col2 = st.columns(2)

with col1:
    st.plotly_chart(
        donut_chart(
            "Copper — source-type distribution",
            list(cu_source.keys()),
            list(cu_source.values())
        ),
        use_container_width=True
    )

with col2:
    st.plotly_chart(
        donut_chart(
            "Nickel — source-type distribution",
            list(ni_source.keys()),
            list(ni_source.values())
        ),
        use_container_width=True
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
st.plotly_chart(fig_val_global, use_container_width=True)

fig_val_source = stacked_bar(
    "Copper — validation by source type",
    list(validation_source.keys()),
    [validation_source[k]["Correct"] for k in validation_source.keys()],
    [validation_source[k]["Partial"] for k in validation_source.keys()],
    [validation_source[k]["Incorrect"] for k in validation_source.keys()]
)
st.plotly_chart(fig_val_source, use_container_width=True)

val_cat_order = ["Production", "Emissions", "Economics", "Energy", "Water", "Waste", "Land", "Other", "Geology"]
fig_val_cat = stacked_bar(
    "Copper — validation by category",
    val_cat_order,
    [validation_category[k]["Correct"] for k in val_cat_order],
    [validation_category[k]["Partial"] for k in val_cat_order],
    [validation_category[k]["Incorrect"] for k in val_cat_order]
)
st.plotly_chart(fig_val_cat, use_container_width=True)

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
Upload the Excel file used for the Cu energy-intensity analysis.
The dashboard will generate:
- the ascending curve for **Cu concentrate**
- the ascending curve for **Cu cathode**
- a combined **bubble plot** for both product types
"""
)

uploaded_file = st.file_uploader("Upload Cu energy-intensity Excel file", type=["xlsx"])

if uploaded_file is not None:
    df = pd.read_excel(uploaded_file)

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

    def format_site(name):
        return "<br>".join(str(name).split())

    colors = {
        "electricity": "#A9CBE8",
        "combined": "#4F81BD",
        "fuel": "#0B3C6D"
    }

    def build_curve(data, title):
        d = data.sort_values("Total intensity", ascending=True).copy()

        d["x_start"] = d["Annual Cu production (t)"].cumsum() - d["Annual Cu production (t)"]
        d["x_center"] = d["x_start"] + d["Annual Cu production (t)"] / 2

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
                ay=-60 if i % 2 == 0 else -100,
                font=dict(size=12)
            )

        total_width = d["Annual Cu production (t)"].sum()

        fig.update_layout(
            barmode="stack",
            template="plotly_white",
            bargap=0,
            title=title,
            xaxis=dict(
                title="Annual Cu production ('000 tonnes)",
                range=[0, total_width]
            ),
            yaxis=dict(title="Energy intensity (GJ/t Cu)"),
            legend=dict(
                orientation="v",
                yanchor="top",
                y=1.0,
                xanchor="left",
                x=0.01
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
                use_container_width=True
            )
        else:
            st.info("No Cu concentrate data found in the uploaded file.")

    with col2:
        if not cath.empty:
            st.plotly_chart(
                build_curve(cath, "Cu cathode — ascending"),
                use_container_width=True
            )
        else:
            st.info("No Cu cathode data found in the uploaded file.")

    # Bubble plot combining both
    bubble_df = pivot.copy()
    fig_bubble = px.scatter(
        bubble_df,
        x="Annual Cu production (t)",
        y="Total intensity",
        color="Main product",
        size="Annual Cu production (t)",
        hover_name="Production site",
        title="Copper energy intensity — combined bubble plot",
        labels={
            "Annual Cu production (t)": "Annual Cu production ('000 tonnes)",
            "Total intensity": "Energy intensity (GJ/t Cu)"
        }
    )
    st.plotly_chart(fig_bubble, use_container_width=True)
else:
    st.info("Upload the Excel file to generate the Cu energy-intensity figures.")
