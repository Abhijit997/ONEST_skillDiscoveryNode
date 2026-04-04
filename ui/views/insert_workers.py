"""
Insert Workers page — manual form entry + CSV upload (TODO).
"""

import hashlib

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

            col3, col4 = st.columns(2)
            with col3:
                phone = st.text_input("Phone *", placeholder="+919876543210")
            with col4:
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

            geo1, geo2 = st.columns(2)
            with geo1:
                latitude = st.number_input("Latitude", min_value=-90.0, max_value=90.0, value=0.0, format="%.6f")
            with geo2:
                longitude = st.number_input("Longitude", min_value=-180.0, max_value=180.0, value=0.0, format="%.6f")

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
            ver1, ver2, ver3 = st.columns(3)
            with ver1:
                aadhaar_verified = st.checkbox("Aadhaar Verified")
            with ver2:
                phone_verified = st.checkbox("Phone Verified")
            with ver3:
                address_verified = st.checkbox("Address Verified")

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

            if errors:
                for e in errors:
                    st.error(e)
            else:
                payload = {
                    "name": name.strip(),
                    "aadhar_hash": _hash_aadhar(aadhar_raw),
                    "phone": phone.strip(),
                    "experience_years": experience_years if experience_years > 0 else None,
                    "district": district.strip(),
                    "taluk": taluk.strip() or None,
                    "city_village": city_village.strip() or None,
                    "latitude": latitude if latitude != 0.0 else None,
                    "longitude": longitude if longitude != 0.0 else None,
                    "skill_category": skill_category,
                    "iti_nsqf_level": iti_nsqf_level,
                    "highest_qualification": highest_qualification.strip() or None,
                    "availability_status": availability_status,
                    "preferred_shift": preferred_shift,
                    "verification_status": {
                        "aadhaar_verified": aadhaar_verified,
                        "phone_verified": phone_verified,
                        "address_verified": address_verified,
                        "phone_conversation": [],
                    },
                    "source_channel": source_channel,
                }

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
