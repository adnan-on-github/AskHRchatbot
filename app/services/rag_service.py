from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator

from langchain_chroma import Chroma
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.memory import ConversationBufferWindowMemory
from langchain.chains import ConversationalRetrievalChain
from langchain.prompts import PromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate, ChatPromptTemplate
from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.embeddings import Embeddings
from loguru import logger

from app.core.config import get_settings

# ── HR-focused system prompt ─────────────────────────────────────────────
_SYSTEM_TEMPLATE = """You are AskHR, a helpful and professional HR assistant.
Your role is to answer employee questions about company policies, benefits,
leave management, payroll, onboarding, and any other HR-related topics.

Use ONLY the context provided below to answer the question.
If the answer is not in the context, say:
"I'm sorry, I don't have that information. Please contact your HR team directly."

Do NOT make up policies or information that isn't in the context.
Be concise, empathetic, and professional.

Context:
{context}
"""

_HUMAN_TEMPLATE = "{question}"


def build_embeddings(settings=None) -> Embeddings:
    """Build an Embeddings instance from settings (respects embedding_provider)."""
    if settings is None:
        settings = get_settings()
    if settings.embedding_provider == "huggingface":
        from langchain_huggingface import HuggingFaceEmbeddings
        logger.info("Embeddings provider: HuggingFace | model={}", settings.hf_embedding_model)
        return HuggingFaceEmbeddings(model_name=settings.hf_embedding_model)
    # Default: OpenAI
    logger.info("Embeddings provider: OpenAI | model={}", settings.embedding_model)
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.openai_api_key,
    )


class RAGService:
    """Manages the conversational RAG chain and per-session chat memory."""

    def __init__(self) -> None:
        self.settings = get_settings()
        # session_id -> {"memory": ConversationBufferWindowMemory, "provider": str, "hf_access_mode": str}
        self._sessions: dict[str, dict[str, Any]] = {}
        # (provider, hf_access_mode) -> BaseChatModel — cached LLM instances
        self._llm_cache: dict[tuple[str, str], BaseChatModel] = {}

        self.embeddings = build_embeddings(self.settings)
        self.vectorstore = Chroma(
            collection_name=self.settings.chroma_collection_name,
            embedding_function=self.embeddings,
            persist_directory=self.settings.chroma_persist_dir,
        )

        # Build the shared chat prompt
        messages = [
            SystemMessagePromptTemplate(
                prompt=PromptTemplate(
                    input_variables=["context"],
                    template=_SYSTEM_TEMPLATE,
                )
            ),
            HumanMessagePromptTemplate(
                prompt=PromptTemplate(
                    input_variables=["question"],
                    template=_HUMAN_TEMPLATE,
                )
            ),
        ]
        self.combine_docs_prompt = ChatPromptTemplate(
            input_variables=["context", "question"],
            messages=messages,
        )

        logger.info(
            "RAGService initialised | default_provider={} embedding_provider={}",
            self.settings.llm_provider,
            self.settings.embedding_provider,
        )

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    async def chat(
        self,
        session_id: str,
        message: str,
        provider: str = "openai",
        hf_access_mode: str = "api",
    ) -> tuple[str, list[Document]]:
        """Return (answer, source_documents) for a given session + message."""
        memory = self._get_or_create_memory(session_id, provider, hf_access_mode)
        llm = self._get_or_build_llm(provider, hf_access_mode)
        chain = self._build_chain(llm, memory)

        logger.info(
            "Chat | session={} provider={} message_len={}",
            session_id, provider, len(message),
        )
        result = await chain.ainvoke({"question": message})

        answer: str = result.get("answer", "")
        source_docs: list[Document] = result.get("source_documents", [])

        logger.debug(
            "Chat | session={} answer_len={} sources={}",
            session_id, len(answer), len(source_docs),
        )
        return answer, source_docs

    async def stream_chat(
        self,
        session_id: str,
        message: str,
        provider: str = "openai",
        hf_access_mode: str = "api",
    ) -> AsyncGenerator[str, None]:
        """Yield answer tokens one by one, then yield a final sentinel with sources."""
        from langchain.callbacks.streaming_aiter import AsyncIteratorCallbackHandler

        callback = AsyncIteratorCallbackHandler()
        memory = self._get_or_create_memory(session_id, provider, hf_access_mode)

        # Build a streaming-enabled LLM with the callback attached
        streaming_llm = self._build_streaming_llm(provider, hf_access_mode, callback)
        chain = self._build_chain(streaming_llm, memory)

        task = asyncio.ensure_future(chain.ainvoke({"question": message}))

        async for token in callback.aiter():
            yield token

        result = await task
        source_docs: list[Document] = result.get("source_documents", [])

        sources_payload = [
            {
                "source": doc.metadata.get("source", "unknown"),
                "page": doc.metadata.get("page"),
                "content_preview": doc.page_content[:200],
            }
            for doc in source_docs
        ]
        yield f"\n__SOURCES__{json.dumps(sources_payload)}"

    def clear_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        logger.info("Cleared memory for session={}", session_id)

    # ------------------------------------------------------------------ #
    # Private — LLM factory                                               #
    # ------------------------------------------------------------------ #

    def _get_or_build_llm(self, provider: str, hf_access_mode: str) -> BaseChatModel:
        """Return a cached (non-streaming) LLM for the given provider/mode."""
        key = (provider, hf_access_mode)
        if key not in self._llm_cache:
            self._llm_cache[key] = self._build_llm(provider, hf_access_mode, streaming=False)
            logger.info("Built LLM | provider={} hf_access_mode={}", provider, hf_access_mode)
        return self._llm_cache[key]

    def _build_llm(
        self, provider: str, hf_access_mode: str, streaming: bool = False, callbacks=None
    ) -> BaseChatModel:
        """Construct a LLM for the given provider and access mode."""
        if provider == "huggingface":
            return self._build_hf_llm(hf_access_mode, streaming=streaming, callbacks=callbacks)
        # Default: OpenAI
        return ChatOpenAI(
            model=self.settings.llm_model,
            temperature=self.settings.llm_temperature,
            api_key=self.settings.openai_api_key,
            streaming=streaming,
            callbacks=callbacks or [],
        )

    def _build_hf_llm(
        self, hf_access_mode: str, streaming: bool = False, callbacks=None
    ) -> BaseChatModel:
        """Build a HuggingFace LLM — either via Inference API or local pipeline."""
        from langchain_huggingface import ChatHuggingFace

        if hf_access_mode == "local":
            from langchain_huggingface import HuggingFacePipeline
            logger.info(
                "Loading HF model locally | model={}", self.settings.hf_llm_model
            )
            pipeline = HuggingFacePipeline.from_model_id(
                model_id=self.settings.hf_llm_model,
                task="text-generation",
                pipeline_kwargs={
                    "temperature": self.settings.llm_temperature,
                    "max_new_tokens": 1024,
                    "do_sample": True,
                },
            )
            return ChatHuggingFace(llm=pipeline, callbacks=callbacks or [])
        else:
            # Inference API (default)
            from langchain_huggingface import HuggingFaceEndpoint
            logger.info(
                "Using HF Inference API | model={}", self.settings.hf_llm_model
            )
            endpoint = HuggingFaceEndpoint(
                repo_id=self.settings.hf_llm_model,
                huggingfacehub_api_token=self.settings.hf_api_token,
                temperature=self.settings.llm_temperature,
                max_new_tokens=1024,
                streaming=streaming,
                callbacks=callbacks or [],
            )
            return ChatHuggingFace(llm=endpoint, callbacks=callbacks or [])

    def _build_streaming_llm(
        self, provider: str, hf_access_mode: str, callback
    ) -> BaseChatModel:
        """Always create a fresh LLM instance with the streaming callback attached."""
        return self._build_llm(provider, hf_access_mode, streaming=True, callbacks=[callback])

    # ------------------------------------------------------------------ #
    # Private — chain & memory                                            #
    # ------------------------------------------------------------------ #

    def _build_chain(
        self, llm: BaseChatModel, memory: ConversationBufferWindowMemory
    ) -> ConversationalRetrievalChain:
        retriever = self.vectorstore.as_retriever(
            search_type="mmr",
            search_kwargs={
                "k": self.settings.retriever_k,
                "fetch_k": self.settings.retriever_k * 3,
            },
        )
        return ConversationalRetrievalChain.from_llm(
            llm=llm,
            retriever=retriever,
            memory=memory,
            combine_docs_chain_kwargs={"prompt": self.combine_docs_prompt},
            return_source_documents=True,
            verbose=False,
        )

    def _get_or_create_memory(
        self, session_id: str, provider: str, hf_access_mode: str
    ) -> ConversationBufferWindowMemory:
        session = self._sessions.get(session_id)
        if session is None:
            memory = ConversationBufferWindowMemory(
                k=self.settings.memory_window,
                memory_key="chat_history",
                output_key="answer",
                return_messages=True,
            )
            self._sessions[session_id] = {
                "memory": memory,
                "provider": provider,
                "hf_access_mode": hf_access_mode,
            }
            logger.debug(
                "Created new memory | session={} provider={}", session_id, provider
            )
        else:
            if session["provider"] != provider or session["hf_access_mode"] != hf_access_mode:
                # Provider changed mid-session — update metadata, preserve memory
                logger.info(
                    "Provider switched | session={} {}:{} -> {}:{}",
                    session_id,
                    session["provider"], session["hf_access_mode"],
                    provider, hf_access_mode,
                )
                session["provider"] = provider
                session["hf_access_mode"] = hf_access_mode
        return self._sessions[session_id]["memory"]


# Module-level singleton — initialised once at app startup
_rag_service: RAGService | None = None


def get_rag_service() -> RAGService:
    global _rag_service
    if _rag_service is None:
        raise RuntimeError("RAGService not initialised. Call init_rag_service() first.")
    return _rag_service


def init_rag_service() -> RAGService:
    global _rag_service
    _rag_service = RAGService()
    return _rag_service
