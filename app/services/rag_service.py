from __future__ import annotations

from typing import AsyncGenerator

from langchain_chroma import Chroma
from langchain_openai import ChatOpenAI, OpenAIEmbeddings, AzureChatOpenAI, AzureOpenAIEmbeddings
from langchain.memory import ConversationBufferWindowMemory
from langchain.chains import ConversationalRetrievalChain
from langchain.prompts import PromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate, ChatPromptTemplate
from langchain_core.documents import Document
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


class RAGService:
    """Manages the conversational RAG chain and per-session chat memory."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._sessions: dict[str, ConversationBufferWindowMemory] = {}

        self.embeddings = self._build_embeddings()
        self.vectorstore = Chroma(
            collection_name=self.settings.chroma_collection_name,
            embedding_function=self.embeddings,
            persist_directory=self.settings.chroma_persist_dir,
        )
        self.llm = self._build_llm(streaming=True)

        # Build the chat prompt
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

        mode = "Azure OpenAI (Managed Identity)" if self.settings.use_managed_identity else (
            "Azure OpenAI (API key)" if self.settings.is_azure else "OpenAI"
        )
        logger.info("RAGService initialised | mode={}", mode)

    # ------------------------------------------------------------------ #
    # LLM / Embeddings factory                                             #
    # ------------------------------------------------------------------ #

    def _build_embeddings(self):
        if self.settings.is_azure:
            kwargs = dict(
                azure_deployment=self.settings.azure_openai_embedding_deployment,
                azure_endpoint=self.settings.azure_openai_endpoint,
                api_version=self.settings.azure_openai_api_version,
            )
            if self.settings.use_managed_identity:
                from app.core.azure_auth import get_token_provider
                kwargs["azure_ad_token_provider"] = get_token_provider()
            else:
                kwargs["api_key"] = self.settings.azure_openai_api_key
            return AzureOpenAIEmbeddings(**kwargs)
        return OpenAIEmbeddings(
            model=self.settings.embedding_model,
            api_key=self.settings.openai_api_key,
        )

    def _build_llm(self, streaming: bool = False):
        if self.settings.is_azure:
            kwargs = dict(
                azure_deployment=self.settings.azure_openai_chat_deployment,
                azure_endpoint=self.settings.azure_openai_endpoint,
                api_version=self.settings.azure_openai_api_version,
                temperature=self.settings.llm_temperature,
                streaming=streaming,
            )
            if self.settings.use_managed_identity:
                from app.core.azure_auth import get_token_provider
                kwargs["azure_ad_token_provider"] = get_token_provider()
            else:
                kwargs["api_key"] = self.settings.azure_openai_api_key
            return AzureChatOpenAI(**kwargs)
        return ChatOpenAI(
            model=self.settings.llm_model,
            temperature=self.settings.llm_temperature,
            api_key=self.settings.openai_api_key,
            streaming=streaming,
        )

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    async def chat(
        self, session_id: str, message: str
    ) -> tuple[str, list[Document]]:
        """Return (answer, source_documents) for a given session + message."""
        memory = self._get_or_create_memory(session_id)
        retriever = self.vectorstore.as_retriever(
            search_type="mmr",
            search_kwargs={
                "k": self.settings.retriever_k,
                "fetch_k": self.settings.retriever_k * 3,
            },
        )
        chain = ConversationalRetrievalChain.from_llm(
            llm=self.llm,
            retriever=retriever,
            memory=memory,
            combine_docs_chain_kwargs={"prompt": self.combine_docs_prompt},
            return_source_documents=True,
            verbose=False,
        )

        logger.info("Chat | session={} message_len={}", session_id, len(message))
        result = await chain.ainvoke({"question": message})

        answer: str = result.get("answer", "")
        source_docs: list[Document] = result.get("source_documents", [])

        logger.debug(
            "Chat | session={} answer_len={} sources={}",
            session_id,
            len(answer),
            len(source_docs),
        )
        return answer, source_docs

    async def stream_chat(
        self, session_id: str, message: str
    ) -> AsyncGenerator[str, None]:
        """Yield answer tokens one by one, then yield a final sentinel with sources."""
        from langchain.callbacks.streaming_aiter import AsyncIteratorCallbackHandler

        callback = AsyncIteratorCallbackHandler()
        memory = self._get_or_create_memory(session_id)
        retriever = self.vectorstore.as_retriever(
            search_type="mmr",
            search_kwargs={
                "k": self.settings.retriever_k,
                "fetch_k": self.settings.retriever_k * 3,
            },
        )

        streaming_llm = self._build_llm(streaming=True)
        streaming_llm.callbacks = [callback]

        chain = ConversationalRetrievalChain.from_llm(
            llm=streaming_llm,
            retriever=retriever,
            memory=memory,
            combine_docs_chain_kwargs={"prompt": self.combine_docs_prompt},
            return_source_documents=True,
            verbose=False,
        )

        import asyncio

        task = asyncio.ensure_future(chain.ainvoke({"question": message}))

        async for token in callback.aiter():
            yield token

        result = await task
        source_docs: list[Document] = result.get("source_documents", [])

        # Yield a special JSON sentinel so the client knows sources
        import json

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
    # Private                                                              #
    # ------------------------------------------------------------------ #

    def _get_or_create_memory(
        self, session_id: str
    ) -> ConversationBufferWindowMemory:
        if session_id not in self._sessions:
            self._sessions[session_id] = ConversationBufferWindowMemory(
                k=self.settings.memory_window,
                memory_key="chat_history",
                output_key="answer",
                return_messages=True,
            )
            logger.debug("Created new memory for session={}", session_id)
        return self._sessions[session_id]


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
