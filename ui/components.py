"""
Reusable UI display helpers for variant cards, toggle bars, and data tables.
"""
import streamlit as st
from typing import Dict, Any, List





def render_variant_table(var_list: List[Dict[str, Any]], title: str = ""):
    """Render a variant list as a clean dataframe."""
    if not var_list:
        st.info("No variants in this category.")
        return

    display = []
    for v in var_list:
        display.append({
            "Variant": v.get("variant", "N/A"),
            "Gene": v.get("gene", "Unknown"),
            "Location": v.get("location", ""),
            "Change": v.get("ref_alt", ""),
            "Significance": v.get("clinical_sig", "N/A"),
            "AF": f"{v['af']:.5f}" if v.get("af") is not None else "—",
        })
    st.dataframe(display, use_container_width=True, hide_index=True)


def render_priority_tabs(prioritized: Dict[str, Any]):
    """Render the 4 priority category tabs + gene cluster warnings."""
    d = prioritized.get("dangerous", [])
    p = prioritized.get("possibly_harmful", [])
    v = prioritized.get("vus", [])
    b = prioritized.get("benign", [])

    tab_d, tab_p, tab_v, tab_b = st.tabs([
        f"🔴 Dangerous ({len(d)})",
        f"🟡 Possibly Harmful ({len(p)})",
        f"🔵 VUS ({len(v)})",
        f"🟢 Benign ({len(b)})",
    ])

    with tab_d:
        render_variant_table(d)
    with tab_p:
        render_variant_table(p)
    with tab_v:
        render_variant_table(v)
    with tab_b:
        render_variant_table(b)

    # Gene cluster warnings
    clusters = prioritized.get("gene_clusters", [])
    if clusters:
        st.markdown("#### ⚠️ Suspicious Gene Clusters")
        for c in clusters:
            st.warning(f"**{c['gene']}** — {c['variant_count']} variants detected "
                       f"(categories: {', '.join(c['categories'])}). {c['note']}")


def render_thinking_block(response_text: str):
    """
    Parse <clinical_thinking> tags from response, render thinking in
    collapsed expander and the clean report below. Returns report_content.
    """
    import re
    thinking_content = ""
    report_content = response_text

    match = re.search(r'<clinical_thinking>(.*?)</clinical_thinking>', response_text, re.DOTALL)
    if match:
        thinking_content = match.group(1).strip()
        report_content = response_text.replace(match.group(0), "").strip()

    if thinking_content:
        with st.expander("🧑‍⚕️ Clinical Reasoning & Extended Thinking (click to expand)", expanded=False):
            st.markdown(thinking_content)

    return report_content
