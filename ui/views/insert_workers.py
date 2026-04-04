"""
Insert Workers page — manual form entry + CSV upload (TODO).
"""

import hashlib
from datetime import date

import requests
import streamlit as st

API_BASE = "http://localhost:8000/api"

SKILL_CATEGORIES = [
    "plumbing", "electrical", "carpentry", "welding", "masonry",
    "painting", "hvac", "tailoring", "driving", "cooking",
    "housekeeping", "gardening", "security", "delivery",
    "construction", "mechanic", "beauty", "other",
]

SOURCE_CHANNELS = ["manual", "csv", "telegram", "chat_simulator", "api"]

AVAILABILITY_STATUSES = ["available", "unavailable", "partially_available"]

PREFERRED_SHIFTS = ["morning", "afternoon", "evening", "night", "flexible"]

# ISO 3166-2:IN  — used for the State dropdown
INDIA_STATES = {
    "AN": "Andaman & Nicobar Islands",
    "AP": "Andhra Pradesh",
    "AR": "Arunachal Pradesh",
    "AS": "Assam",
    "BR": "Bihar",
    "CH": "Chandigarh",
    "CG": "Chhattisgarh",
    "DN": "Dadra & Nagar Haveli and Daman & Diu",
    "DL": "Delhi",
    "GA": "Goa",
    "GJ": "Gujarat",
    "HR": "Haryana",
    "HP": "Himachal Pradesh",
    "JK": "Jammu & Kashmir",
    "JH": "Jharkhand",
    "KA": "Karnataka",
    "KL": "Kerala",
    "LA": "Ladakh",
    "LD": "Lakshadweep",
    "MP": "Madhya Pradesh",
    "MH": "Maharashtra",
    "MN": "Manipur",
    "ML": "Meghalaya",
    "MZ": "Mizoram",
    "NL": "Nagaland",
    "OD": "Odisha",
    "PY": "Puducherry",
    "PB": "Punjab",
    "RJ": "Rajasthan",
    "SK": "Sikkim",
    "TN": "Tamil Nadu",
    "TS": "Telangana",
    "TR": "Tripura",
    "UP": "Uttar Pradesh",
    "UK": "Uttarakhand",
    "WB": "West Bengal",
}
# Dropdown display list:  "KA — Karnataka", with a blank first option
_STATE_OPTIONS = [""] + [f"{code} \u2014 {name}" for code, name in INDIA_STATES.items()]


def _hash_aadhar(raw: str) -> str:
    """SHA-256 hash of the raw Aadhaar number (stripped of spaces/dashes)."""
    cleaned = raw.replace(" ", "").replace("-", "")
    return hashlib.sha256(cleaned.encode()).hexdigest()


def render():
    st.title("➕ Insert Workers")

    tab_manual, tab_csv = st.tabs(["📝 Manual Entry", "📁 CSV / Excel Upload"])

    # ──────────────────────────────────────────
    # Tab 1: Manual Entry
    # ──────────────────────────────────────────
    with tab_manual:
        st.subheader("Enter Worker Details")

        with st.form("worker_form", clear_on_submit=True):
            # ── Personal info ──
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Name *", placeholder="Ramesh Kumar")
            with col2:
                aadhar_raw = st.text_input(
                    "Aadhaar Number *",
                    placeholder="1234 5678 9012",
                    help="Will be SHA-256 hashed before sending. Raw number is never stored.",
                )

            col_dob, col_phone, col_exp = st.columns(3)
            with col_dob:
                dob = st.date_input(
                    "Date of Birth",
                    value=None,
                    min_value=date(1940, 1, 1),
                    max_value=date.today(),
                    help="Worker's date of birth (optional)",
                )
            with col_phone:
                phone = st.text_input("Phone *", placeholder="+919876543210")
            with col_exp:
                experience_years = st.number_input(
                    "Experience (years)", min_value=0.0, max_value=50.0, value=0.0, step=0.5
                )

            # ── Location ──
            st.markdown("##### 📍 Location")
            loc1, loc2, loc3 = st.columns(3)
            with loc1:
                district = st.text_input("District *", placeholder="Bengaluru Urban")
            with loc2:
                taluk = st.text_input("Taluk (optional)", placeholder="Anekal")
            with loc3:
                city_village = st.text_input("City / Village (optional)", placeholder="Chandapura")

            state1, state2 = st.columns([2, 1])
            with state1:
                state_selection = st.selectbox(
                    "State (optional)",
                    options=_STATE_OPTIONS,
                    index=0,
                    help="Leave blank to auto-fill from PIN code on submit.",
                )
            with state2:
                # Show resolved code as read-only feedback
                _sel_code = state_selection.split(" \u2014 ")[0] if state_selection else ""
                st.text_input("ISO Code", value=_sel_code, disabled=True)

            # ── Address details (ONEST compliant) ──
            addr1, addr2, addr3 = st.columns(3)
            with addr1:
                door = st.text_input("Door / Flat No (optional)", placeholder="#12")
            with addr2:
                building = st.text_input("Building / Complex (optional)", placeholder="Sri Apartments")
            with addr3:
                street = st.text_input("Street (optional)", placeholder="MG Road")

            addr4, addr5, addr6 = st.columns(3)
            with addr4:
                locality = st.text_input("Locality / Area (optional)", placeholder="Indiranagar")
            with addr5:
                ward = st.text_input("Ward (optional)", placeholder="Ward 56")
            with addr6:
                area_code = st.text_input("PIN / ZIP Code *", placeholder="560038")

            geo1, geo2 = st.columns(2)
            with geo1:
                latitude = st.number_input(
                    "Latitude",
                    min_value=-90.0, max_value=90.0,
                    value=0.0,
                    format="%.6f",
                    help="Leave at 0 to auto-fill from PIN code on submit.",
                )
            with geo2:
                longitude = st.number_input(
                    "Longitude",
                    min_value=-180.0, max_value=180.0,
                    value=0.0,
                    format="%.6f",
                    help="Leave at 0 to auto-fill from PIN code on submit.",
                )

            # ── Skills & Qualification ──
            st.markdown("##### 🛠️ Skills & Qualification")
            sk1, sk2 = st.columns(2)
            with sk1:
                skill_category = st.selectbox("Skill Category *", options=SKILL_CATEGORIES)
            with sk2:
                iti_nsqf_level = st.selectbox("ITI / NSQF Level", options=[None, 1, 2, 3, 4, 5], index=0)

            highest_qualification = st.text_input(
                "Highest Qualification (optional)", placeholder="ITI Plumbing"
            )

            # ── Availability ──
            st.markdown("##### 📅 Availability")
            av1, av2 = st.columns(2)
            with av1:
                availability_status = st.selectbox("Availability Status", options=AVAILABILITY_STATUSES)
            with av2:
                preferred_shift = st.selectbox("Preferred Shift", options=PREFERRED_SHIFTS, index=4)

            # ── Verification (JSON) ──
            st.markdown("##### ✅ Verification Status")
            ver1, ver2 = st.columns(2)
            with ver1:
                aadhaar_verified = st.checkbox("Aadhaar Verified")
            with ver2:
                phone_verified = st.checkbox("Phone Verified")

            # ── Source & dedup toggle ──
            st.markdown("##### ⚙️ Options")
            opt1, opt2 = st.columns(2)
            with opt1:
                st.text_input("Source Channel", value="manual", disabled=True)
                source_channel = "manual"
            with opt2:
                use_upsert = st.checkbox(
                    "Dedup (mark previous records as old_duplicate)",
                    value=True,
                    help="Uses the /upsert endpoint which marks older records with "
                         "the same Aadhaar hash as old_duplicate.",
                )

            submitted = st.form_submit_button("🚀 Submit Worker", use_container_width=True)

        # ── Handle submission ──
        if submitted:
            # Validate required fields
            errors = []
            if not name.strip():
                errors.append("Name is required.")
            if not aadhar_raw.strip():
                errors.append("Aadhaar number is required.")
            else:
                cleaned = aadhar_raw.replace(" ", "").replace("-", "")
                if not cleaned.isdigit() or len(cleaned) != 12:
                    errors.append("Aadhaar must be exactly 12 digits.")
            if not phone.strip():
                errors.append("Phone is required.")
            if not district.strip():
                errors.append("District is required.")
            if not area_code.strip():
                errors.append("PIN / ZIP Code is required.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                payload = {
                    "name": name.strip(),
                    "dob": dob.isoformat() if dob else None,
                    "aadhar_hash": _hash_aadhar(aadhar_raw),
                    "phone": phone.strip(),
                    "experience_years": experience_years if experience_years > 0 else None,
                    "district": district.strip(),
                    "taluk": taluk.strip() or None,
                    "city_village": city_village.strip() or None,
                    "state_name": INDIA_STATES.get(_sel_code) if _sel_code else None,
                    "state_code": _sel_code or None,
                    "door": door.strip() or None,
                    "building": building.strip() or None,
                    "street": street.strip() or None,
                    "locality": locality.strip() or None,
                    "ward": ward.strip() or None,
                    "area_code": area_code.strip(),
                    "latitude": latitude if latitude != 0.0 else None,
                    "longitude": longitude if longitude != 0.0 else None,
                    "skill_category": skill_category,
                }

                # Auto-fill lat/lon and state from PIN code when left blank
                _need_geo = (
                    payload["latitude"] is None
                    or payload["longitude"] is None
                    or not payload["state_name"]
                    or not payload["state_code"]
                )
                if _need_geo and payload["area_code"]:
                    import math
                    import pgeocode as _pgeocode
                    _nomi = _pgeocode.Nominatim("IN")
                    _row = _nomi.query_postal_code(payload["area_code"])
                    if _row is not None and not (
                        isinstance(_row.latitude, float) and math.isnan(_row.latitude)
                    ):
                        if payload["latitude"] is None:
                            payload["latitude"] = round(float(_row.latitude), 6)
                        if payload["longitude"] is None:
                            payload["longitude"] = round(float(_row.longitude), 6)
                        # Resolve ISO state code via numeric→ISO bridge
                        if not payload["state_code"] or not payload["state_name"]:
                            _PGEOCODE_NUM_TO_ISO = {
                                "1":"AN","2":"AP","30":"AR","3":"AS","34":"BR",
                                "5":"CH","37":"CG","52":"DN","7":"DL","33":"GA",
                                "9":"GJ","10":"HR","11":"HP","12":"JK","38":"JH",
                                "19":"KA","13":"KL","14":"LD","35":"MP","16":"MH",
                                "17":"MN","18":"ML","31":"MZ","20":"NL","21":"OD",
                                "22":"PY","23":"PB","24":"RJ","29":"SK","25":"TN",
                                "40":"TS","26":"TR","36":"UP","39":"UK","28":"WB",
                            }
                            sc = _row.state_code
                            if sc is not None and not (isinstance(sc, float) and math.isnan(sc)):
                                iso = _PGEOCODE_NUM_TO_ISO.get(str(int(float(sc))))
                                if iso:
                                    if not payload["state_code"]:
                                        payload["state_code"] = iso
                                    if not payload["state_name"]:
                                        payload["state_name"] = INDIA_STATES.get(iso)
                        pn = _row.place_name
                        place = str(pn).strip() if pn and not (
                            isinstance(pn, float) and math.isnan(pn)) else None
                        if place:
                            st.info(
                                f"📍 Auto-filled from PIN {payload['area_code']}: "
                                f"**{place}**, {payload.get('state_name', '')} "
                                f"({payload['latitude']}, {payload['longitude']})"
                            )

                payload.update({
                    "iti_nsqf_level": iti_nsqf_level,
                    "highest_qualification": highest_qualification.strip() or None,
                    "availability_status": availability_status,
                    "preferred_shift": preferred_shift,
                    "verification_status": {
                        "aadhaar_verified": aadhaar_verified,
                        "phone_verified": phone_verified,
                        "phone_conversation": [],
                    },
                    "source_channel": source_channel,
                })

                endpoint = "/workers/stage/upsert" if use_upsert else "/workers/stage"

                try:
                    resp = requests.post(f"{API_BASE}{endpoint}", json=payload, timeout=10)
                    if resp.status_code in (200, 201):
                        data = resp.json()
                        st.success("✅ Worker inserted successfully!")

                        if use_upsert:
                            worker = data.get("worker", data)
                            dupes = data.get("duplicates_marked", 0)
                            if dupes > 0:
                                st.info(f"ℹ️ {dupes} previous record(s) marked as old_duplicate.")
                        else:
                            worker = data

                        with st.expander("View inserted record", expanded=True):
                            st.json(worker)
                    else:
                        st.error(f"❌ API error {resp.status_code}")
                        st.json(resp.json())
                except requests.ConnectionError:
                    st.error("❌ Cannot connect to backend. Is the FastAPI server running on port 8000?")
                except Exception as exc:
                    st.error(f"❌ Unexpected error: {exc}")

    # ──────────────────────────────────────────
    # Tab 2: CSV / Excel Upload (TODO)
    # ──────────────────────────────────────────
    with tab_csv:
        st.subheader("Upload CSV / Excel File")
        st.info("🚧 **Coming soon** — CSV/Excel bulk upload is under development.")

        uploaded_file = st.file_uploader(
            "Choose a CSV or Excel file",
            type=["csv", "xlsx", "xls"],
            disabled=False,
        )

        if uploaded_file is not None:
            st.warning("⚠️ File uploaded but processing is not yet implemented. Stay tuned!")
            # TODO: Parse CSV/Excel, validate columns, call /stage or /stage/upsert in batch
