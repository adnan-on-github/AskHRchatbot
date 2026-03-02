"""Azure credential helpers for Managed Identity authentication."""
from __future__ import annotations

from functools import lru_cache
from typing import Callable

from loguru import logger


@lru_cache(maxsize=1)
def get_token_provider() -> Callable[[], str]:
    """
    Returns an Azure AD bearer token provider scoped to Azure Cognitive Services.

    Used as the `azure_ad_token_provider` argument in LangChain's
    AzureChatOpenAI and AzureOpenAIEmbeddings — no API key needed.

    When AZURE_CLIENT_ID is set, uses that specific user-assigned Managed
    Identity; otherwise falls back to system-assigned or ambient credentials
    (works transparently in local dev via `az login`).
    """
    from azure.identity import ManagedIdentityCredential, DefaultAzureCredential, get_bearer_token_provider
    import os

    client_id = os.environ.get("AZURE_CLIENT_ID")

    if client_id:
        logger.info("Using user-assigned Managed Identity | client_id={}", client_id)
        credential = ManagedIdentityCredential(client_id=client_id)
    else:
        logger.info("Using DefaultAzureCredential (az login / system-assigned MI)")
        credential = DefaultAzureCredential()

    return get_bearer_token_provider(
        credential,
        "https://cognitiveservices.azure.com/.default",
    )
