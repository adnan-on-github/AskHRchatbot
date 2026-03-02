"""AskHR Chatbot — Streamlit frontend.

Connects to the FastAPI backend via SSE streaming for real-time token delivery.
"""
from __future__ import annotations

import json
import os
import uuid

import httpx
import streamlit as st

# ── Config ────────────────────────────────────────────────────────────────
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
CHAT_STREAM_URL = f"{BACKEND_URL}/api/v1/chat"
CHAT_SYNC_URL = f"{BACKEND_URL}/api/v1/chat/sync"
INGEST_URL = f"{BACKEND_URL}/api/v1/ingest"
HEALTH_URL = f"{BACKEND_URL}/health"

# ── Page setup ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AskHR Chatbot",
    page_icon="💼",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ── Session state init ────────────────────────────────────────────────────
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages: list[dict] = []
if "provider" not in st.session_state:
    st.session_state.provider = os.environ.get("LLM_PROVIDER", "openai")
if "hf_access_mode" not in st.session_state:
    st.session_state.hf_access_mode = "api"


# ── Helpers ───────────────────────────────────────────────────────────────

def check_backend_health() -> bool:
    try:
        r = httpx.get(HEALTH_URL, timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def stream_answer(session_id: str, message: str, provider: str = "openai", hf_access_mode: str = "api"):
    """
    Stream tokens from the FastAPI SSE endpoint.
    Yields (token: str | None, sources: list | None).
    Token=None + sources payload signals the end of the stream.
    """
    payload = {
        "session_id": session_id,
        "message": message,
        "provider": provider,
        "hf_access_mode": hf_access_mode,
    }
    with httpx.stream("POST", CHAT_STREAM_URL, json=payload, timeout=120) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line.startswith("data:"):
                continue
            raw = line[len("data:"):].strip()
            if raw == "[DONE]":
                return
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if "error" in data:
                raise RuntimeError(data["error"])

            if data.get("done"):
                yield None, data.get("sources", [])
                return

            if "token" in data:
                yield data["token"], None


def trigger_ingest(urls: list[str] | None = None, reindex: bool = False) -> bool:
    try:
        r = httpx.post(
            INGEST_URL,
            json={"urls": urls, "reindex": reindex},
            timeout=15,
        )
        return r.status_code == 202  # noqa: PLR2004
    except Exception:
        return False


# ── Sidebar ───────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("💼 AskHR")
    st.caption("Your AI-powered HR Assistant")
    st.divider()

    # Backend health indicator
    is_healthy = check_backend_health()
    if is_healthy:
        st.success("Backend: Connected ✓", icon="🟢")
    else:
        st.error("Backend: Unreachable ✗", icon="🔴")

    st.divider()
    st.subheader("🤖 LLM Provider")

    provider_choice = st.radio(
        "Choose provider",
        options=["openai", "huggingface"],
        format_func=lambda x: "OpenAI" if x == "openai" else "HuggingFace",
        index=0 if st.session_state.provider == "openai" else 1,
        horizontal=True,
        label_visibility="collapsed",
    )
    st.session_state.provider = provider_choice

    if provider_choice == "huggingface":
        hf_mode_choice = st.radio(
            "HuggingFace access mode",
            options=["api", "local"],
            format_func=lambda x: "Inference API" if x == "api" else "Local (download weights)",
            index=0 if st.session_state.hf_access_mode == "api" else 1,
            horizontal=True,
        )
        st.session_state.hf_access_mode = hf_mode_choice
        if hf_mode_choice == "api":
            st.caption("Requires `HF_API_TOKEN` set on the backend.")
        else:
            st.caption("⚠️ Local mode downloads model weights — requires significant RAM/VRAM and `transformers`+`torch` installed.")

    st.divider()
    st.subheader("Session")
    st.code(st.session_state.session_id[:8] + "…", language=None)

    if st.button("🗑️ Clear Conversation", use_container_width=True):
        # Notify backend to clear memory
        try:
            httpx.delete(
                f"{BACKEND_URL}/api/v1/chat/{st.session_state.session_id}",
                timeout=5,
            )
        except Exception:
            pass
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.subheader("🛠️ Admin")

    with st.expander("Re-index Documents"):
        reindex_flag = st.checkbox("Wipe & rebuild index", value=False)
        extra_urls_input = st.text_area(
            "Extra URLs (one per line)",
            placeholder="https://example.com/hr-policy",
            height=80,
        )
        if st.button("▶ Run Ingestion", use_container_width=True):
            extra_urls = (
                [u.strip() for u in extra_urls_input.splitlines() if u.strip()]
                or None
            )
            with st.spinner("Triggering ingestion…"):
                ok = trigger_ingest(urls=extra_urls, reindex=reindex_flag)
            if ok:
                st.success("Ingestion started! Check backend logs for progress.")
            else:
                st.error("Failed to trigger ingestion. Is the backend running?")

    st.divider()
    st.caption(
        "Powered by "
        + ("OpenAI GPT-4o" if st.session_state.provider == "openai" else "HuggingFace")
        + " · ChromaDB · LangChain · FastAPI · Streamlit"
    )


# ── Main chat UI ──────────────────────────────────────────────────────────
st.title("💼 AskHR Chatbot")
st.caption("Ask me anything about HR policies, benefits, leave, payroll, and more.")

# Render existing conversation history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            with st.expander(f"📄 Sources ({len(msg['sources'])})"):
                for src in msg["sources"]:
                    st.markdown(
                        f"**{src.get('source', 'Unknown')}**"
                        + (f" — page {src['page']}" if src.get("page") is not None else "")
                    )
                    if src.get("content_preview"):
                        st.caption(src["content_preview"] + "…")

# Chat input
if prompt := st.chat_input("Ask an HR question…", disabled=not is_healthy):
    # Display user message immediately
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Stream assistant response
    with st.chat_message("assistant"):
        answer_placeholder = st.empty()
        full_answer = ""
        sources: list[dict] = []

        try:
            for token, src_payload in stream_answer(
                st.session_state.session_id,
                prompt,
                provider=st.session_state.provider,
                hf_access_mode=st.session_state.hf_access_mode,
            ):
                if token is not None:
                    full_answer += token
                    answer_placeholder.markdown(full_answer + "▌")
                elif src_payload is not None:
                    sources = src_payload

            answer_placeholder.markdown(full_answer)

            if sources:
                with st.expander(f"📄 Sources ({len(sources)})"):
                    for src in sources:
                        st.markdown(
                            f"**{src.get('source', 'Unknown')}**"
                            + (f" — page {src['page']}" if src.get("page") is not None else "")
                        )
                        if src.get("content_preview"):
                            st.caption(src["content_preview"] + "…")

        except Exception as exc:
            full_answer = f"⚠️ Error: {exc}"
            answer_placeholder.error(full_answer)

    # Save assistant turn to history
    st.session_state.messages.append(
        {"role": "assistant", "content": full_answer, "sources": sources}
    )
