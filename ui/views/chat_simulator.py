"""
Phone Verification Chat Simulator — Streamlit page.

Optimised for speed: a single ``GET /chat/state/{worker_id}`` call returns
messages + next question, and ``POST /answer`` returns the updated state so
no extra round-trips are needed. Timeouts are 2 s.
"""

import requests
import streamlit as st

API = "http://localhost:8000/api"
_TIMEOUT = 2  # seconds — keep low for snappy UI


# ── API helpers (all return parsed JSON or None/False) ──


def _fetch_pending(timeout=_TIMEOUT):
    try:
        r = requests.get(f"{API}/chat/pending-workers", timeout=timeout)
        return r.json().get("workers", []) if r.ok else []
    except requests.ConnectionError:
        st.error("Cannot connect to backend — is FastAPI running on :8000?")
    except Exception:
        pass
    return []


def _fetch_state(worker_id: str):
    """Single call that returns messages + next_question."""
    try:
        r = requests.get(f"{API}/chat/state/{worker_id}", timeout=_TIMEOUT)
        if r.ok:
            return r.json()
    except Exception:
        pass
    return None


def _send_msg(worker_id: str, sender: str, message: str):
    try:
        r = requests.post(
            f"{API}/chat/send",
            json={"worker_id": worker_id, "sender": sender, "message": message},
            timeout=_TIMEOUT,
        )
        return r.json() if r.ok else None
    except Exception:
        return None


def _submit_answer(worker_id: str, q_id: str, answer: str):
    try:
        r = requests.post(
            f"{API}/chat/answer",
            json={"worker_id": worker_id, "question_id": q_id, "answer": answer},
            timeout=_TIMEOUT,
        )
        if r.ok:
            return r.json()
        if r.status_code == 422:
            st.warning(r.json().get("detail", "Invalid answer"))
    except Exception:
        pass
    return None


def _mark_verified(worker_id: str):
    try:
        r = requests.post(
            f"{API}/chat/mark-verified",
            json={"worker_id": worker_id},
            timeout=_TIMEOUT,
        )
        return r.json() if r.ok else None
    except Exception:
        return None


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def render():
    st.title("Phone Verification Chat")

    # ── CSS ──
    st.markdown(
        """
        <style>
        .chat-container {
            background: #ece5dd;
            border-radius: 0;
            padding: 16px;
            min-height: 420px;
            max-height: 520px;
            overflow-y: auto;
            margin-bottom: 0;
        }
        .chat-bubble {
            padding: 8px 14px;
            border-radius: 10px;
            margin-bottom: 8px;
            max-width: 75%;
            word-wrap: break-word;
            font-size: 14px;
            line-height: 1.4;
        }
        .chat-bubble.agent {
            background: #dcf8c6;
            margin-left: auto;
            text-align: right;
            border-bottom-right-radius: 2px;
        }
        .chat-bubble.worker {
            background: #fff;
            margin-right: auto;
            text-align: left;
            border-bottom-left-radius: 2px;
        }
        .chat-bubble .sender {
            font-size: 11px; font-weight: bold; color: #075e54; margin-bottom: 2px;
        }
        .chat-bubble .time {
            font-size: 10px; color: #999; margin-top: 4px;
        }
        .chat-header {
            background: #075e54; color: #fff;
            padding: 12px 16px; border-radius: 10px 10px 0 0;
        }
        /* Bordered container = seamless chat window frame */
        [data-testid="stVerticalBlockBorderWrapper"]:has(.chat-header) {
            background: #ece5dd !important;
            border: none !important;
            border-radius: 0 0 10px 10px;
            padding: 0 !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.chat-header)
            > [data-testid="stVerticalBlock"] {
            gap: 0 !important;
            padding-bottom: 10px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if "sel_worker" not in st.session_state:
        st.session_state.sel_worker = None
    if "_cached_state" not in st.session_state:
        st.session_state._cached_state = None      # cached /state or /answer response
    if "_cached_workers" not in st.session_state:
        st.session_state._cached_workers = None     # cached pending-workers list

    col_list, col_chat = st.columns([1, 2.5])

    # ── LEFT: worker list ──
    with col_list:
        st.markdown("### Pending Workers")
        if st.button("Refresh", use_container_width=True):
            st.session_state._cached_workers = None
            st.rerun()

        # Use cached list if available, otherwise fetch
        if st.session_state._cached_workers is not None:
            workers = st.session_state._cached_workers
        else:
            workers = _fetch_pending()
            st.session_state._cached_workers = workers
        if not workers:
            st.info("No workers pending phone verification.")
        else:
            st.caption(f"{len(workers)} worker(s)")
            for w in workers:
                lbl = f"**{w['name']}**  \n{w['phone']}  \n{w['district']} · {w['skill_category']}"
                sel = (
                    st.session_state.sel_worker
                    and st.session_state.sel_worker["worker_id"] == w["worker_id"]
                )
                if st.button(
                    lbl,
                    key=f"w_{w['worker_id']}",
                    use_container_width=True,
                    type="primary" if sel else "secondary",
                ):
                    st.session_state.sel_worker = w
                    st.rerun()

    # ── RIGHT: chat window ──
    with col_chat:
        sel = st.session_state.sel_worker
        if not sel:
            st.markdown(
                '<div style="text-align:center;padding:80px 20px;color:#888;">'
                "<h3>Select a worker to start chatting</h3></div>",
                unsafe_allow_html=True,
            )
            return

        wid = sel["worker_id"]
        wname = sel["name"]
        wphone = sel["phone"]

        # Use cached state (from /answer, /send, etc.) or fetch from DB
        if st.session_state._cached_state and st.session_state._cached_state.get("worker_id") == wid:
            state = st.session_state._cached_state
            st.session_state._cached_state = None   # consume it
        else:
            state = _fetch_state(wid)

        if not state:
            st.error("Could not load chat state.")
            return

        messages = state.get("messages", [])
        nq = state.get("next_question", {})

        # Send greeting only when the conversation is truly empty (first contact)
        if not messages:
            res = _send_msg(wid, "agent",
                            f"Hello {wname}! Welcome to ONEST Skill Discovery. "
                            f"We'd like to verify your phone number and ask a few screening questions.")
            if res:
                state = res
                messages = state.get("messages", [])
                nq = state.get("next_question", {})

        # If all questions already answered (e.g. phone_verified), deselect immediately
        if nq.get("all_answered", False):
            st.session_state.sel_worker = None
            st.session_state._cached_state = None
            st.session_state._cached_workers = None
            st.rerun()
            return

        with st.container(border=True):
            # ── Chat header ──
            st.markdown(
                f'<div class="chat-header">'
                f"<strong>{_esc(wname)}</strong> &middot; {_esc(wphone)}"
                f' <span style="font-size:12px;opacity:.7;">WhatsApp / Call / SMS</span>'
                f"</div>",
                unsafe_allow_html=True,
            )

            # ── Chat bubbles ──
            html = '<div class="chat-container">'
            if not messages:
                html += '<p style="text-align:center;color:#888;">No messages yet.</p>'
            else:
                for m in messages:
                    side = "agent" if m["sender"] == "agent" else "worker"
                    who = "You (Agent)" if side == "agent" else _esc(wname)
                    ts = m.get("timestamp", "")[11:16]
                    html += (
                        f'<div style="display:flex;justify-content:'
                        f"{'flex-end' if side == 'agent' else 'flex-start'};\">"
                        f'<div class="chat-bubble {side}">'
                        f'<div class="sender">{who}</div>'
                        f"{_esc(m['message'])}"
                        f'<div class="time">{ts}</div>'
                        f"</div></div>"
                    )
            html += "</div>"
            st.markdown(html, unsafe_allow_html=True)

            # ── Interactive reply area (inside the chat window) ──
            all_done = nq.get("all_answered", False)
            q_id = nq.get("question_id")
            options = nq.get("options", [])
            ui_type = nq.get("ui_type", "buttons")

            if not all_done and q_id:
                if ui_type == "buttons" and len(options) <= 3:
                    cols = st.columns(len(options))
                    for i, opt in enumerate(options):
                        with cols[i]:
                            if st.button(opt, key=f"a_{q_id}_{i}", use_container_width=True):
                                res = _submit_answer(wid, q_id, opt)
                                if res:
                                    st.session_state._cached_state = res
                                st.rerun()
                else:
                    with st.form(f"lf_{q_id}", clear_on_submit=True):
                        chosen = st.selectbox("Select an answer", options=options, key=f"ls_{q_id}")
                        if st.form_submit_button("Submit", use_container_width=True):
                            res = _submit_answer(wid, q_id, chosen)
                            if res:
                                st.session_state._cached_state = res
                            st.rerun()
            else:
                # Should not normally reach here (early check above handles it)
                st.info("All screening questions answered — phone verified!")

        st.divider()

        # ── Free-text input ──
        with st.expander("Send a free-text message", expanded=False):
            with st.form("ft_form", clear_on_submit=True):
                c1, c2, c3 = st.columns([5, 1.2, 1])
                with c1:
                    txt = st.text_input("Message", placeholder="Type a message...",
                                        label_visibility="collapsed")
                with c2:
                    role = st.selectbox("As", ["agent", "worker"],
                                        label_visibility="collapsed")
                with c3:
                    go = st.form_submit_button("Send", use_container_width=True)
            if go and txt.strip():
                res = _send_msg(wid, role, txt.strip())
                if res:
                    st.session_state._cached_state = res
                st.rerun()


