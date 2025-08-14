
import json
import re
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional

import streamlit as st
from urllib.parse import quote_plus

# --- Streamlit page config MUST be first st.* call ---
st.set_page_config(page_title="Compatibility Checker", page_icon="✅", layout="wide")

# ---------- Load rules ----------
@st.cache_data
def load_rules() -> Dict[str, Any]:
    with open("data/compatibility_rules.json") as f:
        return json.load(f)

RULES = load_rules()

# ---------- Utilities ----------
BRANDS = list(RULES["brands"].keys())
SERIES_TOKENS = {
    # map token -> (brand, series)
    "QO": ("Square D", "QO"),
    "HOMELINE": ("Square D", "Homeline"),
    "HOM": ("Square D", "Homeline"),
    "QP": ("Siemens", "QP"),
    "EATON BR": ("Eaton", "BR"),
    "BR ": ("Eaton", "BR"),
    "EATON CH": ("Eaton", "CH"),
    " CH ": ("Eaton", "CH"),
    "THQL": ("GE", "THQL"),
    "THQP": ("GE", "THQL"),
    "LEVITON": ("Leviton", "Smart"),
}

def brand_series_query(brand: str, series: str) -> str:
    """Build a query string we can append to your CES category URLs."""
    if not brand or not series:
        return ""
    return f"?brand={quote_plus(brand)}&family={quote_plus(series)}"


NEMA_REGEX = re.compile(r"NEMA\s*(\d+X?|\dR)", re.IGNORECASE)
PLUG_REGEX = re.compile(r"NEMA\s*(\d{1,2}-\d{2})", re.IGNORECASE)
VOLT_REGEX = re.compile(r"(\d{3})(?:/\d{3})?\s*V|(\d{3})\s*VAC|(\d{3})\s*Volts", re.IGNORECASE)
AMP_REGEX = re.compile(r"(\d{1,3})\s*A\b", re.IGNORECASE)
PHASE_REGEX = re.compile(r"\b(1[ -]?[PØ]|3[ -]?[PØ]|single[- ]?phase|three[- ]?phase)\b", re.IGNORECASE)
POLE_REGEX = re.compile(r"\b(\d)[ -]?(pole|p)\b", re.IGNORECASE)


@dataclass
class ParsedSpecs:
    product_type: str = ""         # panel, breaker, receptacle, plug, evse, unknown
    brand: str = ""
    series: str = ""
    model: str = ""
    voltage: str = ""
    phase: str = ""
    amps: Optional[int] = None
    poles: Optional[int] = None
    nema_enclosure: str = ""
    plug_config: str = ""          # e.g., NEMA 14-50
    raw_excerpt: str = ""          # for debugging / audit


def detect_product_type(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ["load center", "panelboard", "loadcenter", "panel "]):
        return "panel"
    if "breaker" in t or "circuit breaker" in t:
        return "breaker"
    if "receptacle" in t or "outlet" in t:
        return "receptacle"
    if "plug" in t and "receptacle" not in t:
        return "plug"
    if "ev charger" in t or "evse" in t or "electric vehicle charger" in t:
        return "evse"
    return "unknown"


def parse_product_info(pasted: str) -> ParsedSpecs:
    text = " " + re.sub(r"\s+", " ", pasted).strip() + " "
    ps = ParsedSpecs(raw_excerpt=pasted[:800])

    # Brand & Series heuristic
    for brand in BRANDS:
        if brand.lower() in text.lower():
            ps.brand = brand
            break

    # series tokens
    for token, (brand_guess, series_guess) in SERIES_TOKENS.items():
        if token.lower() in text.lower():
            ps.series = series_guess
            if not ps.brand:
                ps.brand = brand_guess
            break

    # simple model capture (alphanumeric with dashes)
    m_model = re.search(r"\b([A-Z0-9-]{4,})\b", text, re.IGNORECASE)
    if m_model:
        ps.model = m_model.group(1)

    # electrical basics
    m_volt = VOLT_REGEX.search(text)
    if m_volt:
        # pick the first non-None group
        for g in m_volt.groups():
            if g:
                ps.voltage = f"{g}V"
                break

    m_amp = AMP_REGEX.search(text)
    if m_amp:
        try:
            ps.amps = int(m_amp.group(1))
        except:
            pass

    m_phase = PHASE_REGEX.search(text)
    if m_phase:
        token = m_phase.group(0).lower()
        if "3" in token:
            ps.phase = "3Ø"
        else:
            ps.phase = "1Ø"

    m_poles = POLE_REGEX.search(text)
    if m_poles:
        try:
            ps.poles = int(m_poles.group(1))
        except:
            pass

    m_nema = NEMA_REGEX.search(text)
    if m_nema:
        ps.nema_enclosure = m_nema.group(1).upper().replace("R", "3R")

    m_plug = PLUG_REGEX.search(text)
    if m_plug:
        ps.plug_config = f"NEMA {m_plug.group(1)}"

    ps.product_type = detect_product_type(text)
    return ps


def series_breaker_families(brand: str, series: str) -> List[str]:
    brands = RULES.get("brands", {})
    if brand in brands and "series" in brands[brand] and series in brands[brand]["series"]:
        return brands[brand]["series"][series]["breaker_families"]
    return []


def check_panel_breaker_compat(ps_panel: ParsedSpecs, ps_breaker: ParsedSpecs) -> Dict[str, Any]:
    result = {
        "compatible": False,
        "reasons": [],
        "suggestions": []
    }

    if ps_panel.product_type != "panel" or ps_breaker.product_type != "breaker":
        result["reasons"].append("Product types must be a panel and a breaker.")
        return result

    if not ps_panel.brand or not ps_panel.series:
        result["reasons"].append("Panel brand/series not identified.")
        return result

    fams = series_breaker_families(ps_panel.brand, ps_panel.series)
    if not fams:
        result["reasons"].append("No breaker family mapping found for this panel series (expand rules).")
        return result

    # Heuristic: infer breaker family from model tokens
    inferred_family = None
    for fam in fams:
        if fam.lower() in (ps_breaker.model + " " + ps_breaker.series).lower():
            inferred_family = fam
            break

    if inferred_family:
        result["compatible"] = True
    else:
        result["reasons"].append(
            f"Breaker does not appear to be from accepted families for {ps_panel.brand} {ps_panel.series}: {', '.join(fams)}"
        )
        result["suggestions"].append(f"Use breaker family: {', '.join(fams)}")

    # Basic electrical sanity checks
    if ps_breaker.amps and ps_panel.amps and ps_breaker.amps > ps_panel.amps:
        result["reasons"].append("Breaker amp rating exceeds panel main rating; verify application.")

    if ps_panel.phase and ps_breaker.poles:
        # Simple sanity: 3Ø often uses 2P/3P; 1Ø uses 1P/2P. This is not a hard rule, just a hint.
        if ps_panel.phase == "1Ø" and ps_breaker.poles not in (1,2):
            result["reasons"].append("Pole count atypical for single-phase panels (check spec).")
        if ps_panel.phase == "3Ø" and ps_breaker.poles not in (2,3):
            result["reasons"].append("Pole count atypical for three-phase panels (check spec).")

    return result


def check_plug_receptacle(ps_a: ParsedSpecs, ps_b: ParsedSpecs) -> Dict[str, Any]:
    # Match either direction
    A = ps_a.plug_config or ""
    B = ps_b.plug_config or ""
    type_a = ps_a.product_type
    type_b = ps_b.product_type

    details = RULES["plug_receptacle"]
    result = {"compatible": False, "reasons": [], "suggestions": []}

    if type_a == type_b:
        result["reasons"].append("You provided two of the same type. Provide a plug and a receptacle.")
        return result

    config = A or B
    if not config:
        result["reasons"].append("Unable to detect a NEMA configuration like 'NEMA 14-50'.")
        return result

    if config in details:
        # If one side has a known config, assume match if the other is generic receptacle/plug.
        result["compatible"] = True
        result["suggestions"].append(f"Both should be {config}. Verify voltage/amp rating: {details[config]['voltage']} / {details[config]['amps']}A.")
    else:
        result["reasons"].append("NEMA configuration not recognized in rule set (expand rules).")

    return result


def check_enclosure(ps: ParsedSpecs, required_env: str) -> Dict[str, Any]:
    # Compare required environment (e.g., '3R' for outdoor) with product's NEMA enclosure
    result = {"compatible": False, "reasons": [], "suggestions": []}
    if not ps.nema_enclosure:
        result["reasons"].append("Product does not specify a NEMA enclosure rating.")
        return result

    hierarchy = ["1", "3R", "4", "4X"]
    if required_env not in hierarchy or ps.nema_enclosure not in hierarchy:
        result["reasons"].append("Unknown NEMA rating in provided data.")
        return result

    if hierarchy.index(ps.nema_enclosure) >= hierarchy.index(required_env):
        result["compatible"] = True
    else:
        result["reasons"].append(f"NEMA {ps.nema_enclosure} is below required {required_env}.")
        result["suggestions"].append("Select an enclosure rated 3R/4/4X for outdoor/corrosive environments.")

    return result


def ev_breaker_sizing(evse_amp_output: int) -> Dict[str, Any]:
    # 125% rule (simplified): choose next standard breaker size at/above 1.25x
    target = int(round(evse_amp_output * 1.25))
    standard_sizes = [15, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    chosen = next((s for s in standard_sizes if s >= target), None)
    return {
        "evse_output_amps": evse_amp_output,
        "min_circuit_amps": target,
        "recommended_breaker": chosen,
        "note": RULES["ev_charger_rules"]["note"]
    }


def section_header(title: str, subtitle: str = ""):
    st.markdown(f"### {title}")
    if subtitle:
        st.caption(subtitle)


def main():
    
    st.title("Compatibility Checker (v1)")
    st.write("Reduce purchase doubt by verifying that parts work together. Paste specs now; enable URL mode later.")

    with st.expander("Input mode", expanded=True):
        mode = st.radio("Choose how you'll provide product info:", [
            "Paste product information (recommended)",
            "URL (placeholder – disabled until crawling allowed)"
        ], index=0)

        if mode == "URL (placeholder – disabled until crawling allowed)":
            st.text_input("Product URL", placeholder="https://www.example.com/your-product")
            st.info("Your site currently blocks bots. Keep this for later; we’ll wire it when permitted.")

    # --- Paste product info ---
    colA, colB = st.columns(2)
    with colA:
        section_header("Item A")
        a_text = st.text_area("Paste product info, HTML, or spec text (Item A)", height=180, placeholder="e.g., Square D QO load center 1Ø 120/240V, 200A, NEMA 3R")
        btn_a = st.button("Parse Item A")
    with colB:
        section_header("Item B")
        b_text = st.text_area("Paste product info, HTML, or spec text (Item B)", height=180, placeholder="e.g., Square D QO120 breaker 1P 20A")
        btn_b = st.button("Parse Item B")

    if "ps_a" not in st.session_state: st.session_state.ps_a = None
    if "ps_b" not in st.session_state: st.session_state.ps_b = None

    if btn_a and a_text.strip():
        st.session_state.ps_a = parse_product_info(a_text)
    if btn_b and b_text.strip():
        st.session_state.ps_b = parse_product_info(b_text)

    if st.session_state.ps_a or st.session_state.ps_b:
        st.markdown("---")
        section_header("Parsed Specs (editable)")

        def editable(parsed: Optional[ParsedSpecs], label: str) -> Optional[ParsedSpecs]:
            if not parsed:
                st.info(f"No {label} parsed yet.")
                return None
            cols = st.columns(3)
            with cols[0]:
                pt = st.selectbox(f"{label} type", ["unknown", "panel", "breaker", "receptacle", "plug", "evse"], index=["unknown","panel","breaker","receptacle","plug","evse"].index(parsed.product_type))
                brand = st.text_input(f"{label} brand", value=parsed.brand)
                series = st.text_input(f"{label} series", value=parsed.series)
            with cols[1]:
                model = st.text_input(f"{label} model", value=parsed.model)
                voltage = st.text_input(f"{label} voltage", value=parsed.voltage)
                phase = st.text_input(f"{label} phase", value=parsed.phase)
            with cols[2]:
                amps = st.number_input(f"{label} amps", min_value=0, max_value=1000, value=int(parsed.amps or 0), step=5)
                poles = st.number_input(f"{label} poles", min_value=0, max_value=4, value=int(parsed.poles or 0), step=1)
                nema = st.text_input(f"{label} NEMA enclosure", value=parsed.nema_enclosure)
            plug = st.text_input(f"{label} plug configuration (e.g., NEMA 14-50)", value=parsed.plug_config)
            raw = st.text_area(f"{label} raw excerpt (reference)", value=parsed.raw_excerpt, height=80)

            out = ParsedSpecs(
                product_type=pt, brand=brand, series=series, model=model, voltage=voltage,
                phase=phase, amps=(amps or None), poles=(poles or None), nema_enclosure=nema,
                plug_config=plug, raw_excerpt=raw
            )
            return out

        col1, col2 = st.columns(2)
        with col1:
            ps_a = editable(st.session_state.ps_a, "Item A")
        with col2:
            ps_b = editable(st.session_state.ps_b, "Item B")

        st.session_state.ps_a = ps_a
        st.session_state.ps_b = ps_b

        st.markdown("---")
        section_header("Checks")

        # Panel ↔ Breaker
        if ps_a and ps_b:
            if (ps_a.product_type == "panel" and ps_b.product_type == "breaker") or (ps_b.product_type == "panel" and ps_a.product_type == "breaker"):
                panel = ps_a if ps_a.product_type == "panel" else ps_b
                breaker = ps_b if panel == ps_a else ps_a
                res = check_panel_breaker_compat(panel, breaker)
                st.subheader("Panel ↔ Breaker")
                st.write(res)
                if res.get("compatible"):
                    fams = series_breaker_families(panel.brand, panel.series)
                    st.success(f"Compatible. Accepted breaker families for {panel.brand} {panel.series}: {', '.join(fams)}")
                else:
                    for r in res.get("reasons", []):
                        st.error(r)
                    for s in res.get("suggestions", []):
                        st.info(s)

            # Plug ↔ Receptacle
            if {"plug", "receptacle"} == {ps_a.product_type, ps_b.product_type}:
                st.subheader("Plug ↔ Receptacle")
                res2 = check_plug_receptacle(ps_a, ps_b)
                st.write(res2)
                if res2.get("compatible"):
                    st.success("Plug and receptacle appear to match. Verify voltage/amp rating before purchase.")
                else:
                    for r in res2.get("reasons", []):
                        st.error(r)
                    for s in res2.get("suggestions", []):
                        st.info(s)

        # Enclosure check
        st.subheader("Environment / NEMA")
        required_env = st.selectbox("Required environment", ["None", "1", "3R", "4", "4X"], index=0)
        if required_env != "None":
            target = ps_a or ps_b
            if target:
                env_res = check_enclosure(target, required_env)
                st.write(env_res)
                if env_res.get("compatible"):
                    st.success(f"{target.nema_enclosure} meets or exceeds required {required_env}.")
                else:
                    for r in env_res.get("reasons", []):
                        st.error(r)
                    for s in env_res.get("suggestions", []):
                        st.info(s)
            else:
                st.info("Parse at least one item to run enclosure check.")

        # EV Charger helper
        st.subheader("EV Charger Circuit Helper")
        ev_amp = st.number_input("EVSE output current (A)", min_value=0, max_value=100, value=0, step=2, help="Nameplate continuous current output of the charger.")
        if ev_amp:
            ev = ev_breaker_sizing(ev_amp)
            st.write(ev)
            st.success(f"Recommend a breaker around {ev['recommended_breaker']}A (≥ {ev['min_circuit_amps']}A). {ev['note']}")

       st.markdown("---")
section_header("Next steps / CTA")

routes = RULES.get("routes", {})
buttons = []

# Prefer panel context to build deep links
panel = None
breaker = None
if st.session_state.get("ps_a") and st.session_state.ps_a.product_type == "panel":
    panel = st.session_state.ps_a
if st.session_state.get("ps_b") and st.session_state.ps_b.product_type == "panel":
    panel = st.session_state.ps_b
if st.session_state.get("ps_a") and st.session_state.ps_a.product_type == "breaker":
    breaker = st.session_state.ps_a
if st.session_state.get("ps_b") and st.session_state.ps_b.product_type == "breaker":
    breaker = st.session_state.ps_b

q = brand_series_query(panel.brand, panel.series) if panel else ""

# Build buttons based on what the user is checking
if routes.get("breakers"):
    buttons.append(("Shop compatible breakers", routes["breakers"] + q if q else routes["breakers"]))
if routes.get("panels"):
    buttons.append(("Shop matching panels", routes["panels"] + q if q else routes["panels"]))

# Plug / receptacle context
has_plug = any([(st.session_state.get("ps_a") and st.session_state.ps_a.product_type == "plug"),
                (st.session_state.get("ps_b") and st.session_state.ps_b.product_type == "plug")])
has_recept = any([(st.session_state.get("ps_a") and st.session_state.ps_a.product_type == "receptacle"),
                  (st.session_state.get("ps_b") and st.session_state.ps_b.product_type == "receptacle")])
if has_plug and routes.get("receptacles"):
    buttons.append(("Shop matching receptacles", routes["receptacles"]))
if has_recept and routes.get("plugs"):
    buttons.append(("Shop matching plugs", routes["plugs"]))

# EV helper
if routes.get("ev"):
    buttons.append(("Shop EV chargers", routes["ev"]))

# Accessories for panels
if panel and routes.get("accessories"):
    buttons.append(("Panel accessories (hubs, ground bars, covers)", routes["accessories"] + q if q else routes["accessories"]))

# Render buttons 2 per row
for i in range(0, len(buttons), 2):
    c1, c2 = st.columns(2)
    label1, url1 = buttons[i]
    c1.link_button(label1, url1)
    if i + 1 < len(buttons):
        label2, url2 = buttons[i+1]
        c2.link_button(label2, url2)

st.caption(RULES.get("disclaimer", ""))
