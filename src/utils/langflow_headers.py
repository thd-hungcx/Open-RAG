"""Utility functions for building Langflow request headers."""

import os
from typing import Dict
from utils.container_utils import transform_localhost_url


def build_ibm_opensearch_vars(
    credentials: str,
    prefix: str = "X-LANGFLOW-GLOBAL-VAR-",
) -> Dict[str, str]:
    """Build IBM OpenSearch auth vars from a credential string.

    Supports both ``'Basic <b64>'`` (extracts username/password + JWT) and
    ``'Bearer <token>'`` (JWT only, no username/password).

    Pass prefix="X-LANGFLOW-GLOBAL-VAR-" for HTTP headers, or prefix="" for MCP global vars.
    """
    result = {f"{prefix}JWT": credentials}
    if credentials.startswith("Basic "):
        from auth.ibm_auth import extract_ibm_credentials

        username, password = extract_ibm_credentials(credentials)
        result[f"{prefix}OPENSEARCH_USERNAME"] = username
        result[f"{prefix}OPENSEARCH_PASSWORD"] = password
    return result


async def add_provider_credentials_to_headers(
    headers: Dict[str, str],
    config,
    flows_service=None,
    jwt_token: str = None,
) -> None:
    """Add provider credentials to headers as Langflow global variables."""
    # Add OpenAI credentials
    if config.providers.openai.api_key:
        headers["X-LANGFLOW-GLOBAL-VAR-OPENAI_API_KEY"] = str(
            config.providers.openai.api_key
        )

    # Add Anthropic credentials
    if config.providers.anthropic.api_key:
        headers["X-LANGFLOW-GLOBAL-VAR-ANTHROPIC_API_KEY"] = str(
            config.providers.anthropic.api_key
        )

    # Add WatsonX credentials
    if config.providers.watsonx.api_key:
        headers["X-LANGFLOW-GLOBAL-VAR-WATSONX_APIKEY"] = str(
            config.providers.watsonx.api_key
        )

    if config.providers.watsonx.project_id:
        headers["X-LANGFLOW-GLOBAL-VAR-WATSONX_PROJECT_ID"] = str(
            config.providers.watsonx.project_id
        )

    # Add Ollama endpoint (with localhost transformation)
    if config.providers.ollama.endpoint:
        if flows_service:
            ollama_endpoint = await flows_service.resolve_ollama_url(
                config.providers.ollama.endpoint
            )
        else:
            ollama_endpoint = transform_localhost_url(config.providers.ollama.endpoint)
        headers["X-LANGFLOW-GLOBAL-VAR-OLLAMA_BASE_URL"] = str(ollama_endpoint)

    # Inject OpenSearch URL so Langflow flows always use the correct endpoint
    from config.settings import OPENSEARCH_HOST, OPENSEARCH_PORT

    headers["X-LANGFLOW-GLOBAL-VAR-OPENSEARCH_URL"] = (
        f"https://{OPENSEARCH_HOST}:{OPENSEARCH_PORT}"
    )

    # VLM credentials
    vlm_endpoint = os.getenv("VLM_ENDPOINT")
    vlm_model = os.getenv("VLM_MODEL")
    vlm_api_key = os.getenv("VLM_API_KEY")
    if vlm_endpoint:
        headers["X-LANGFLOW-GLOBAL-VAR-VLM_ENDPOINT"] = vlm_endpoint
    if vlm_model:
        headers["X-LANGFLOW-GLOBAL-VAR-VLM_MODEL"] = vlm_model
    if vlm_api_key:
        headers["X-LANGFLOW-GLOBAL-VAR-VLM_API_KEY"] = vlm_api_key

    # IBM mode: inject OpenSearch Basic credentials as separate global vars
    from config.settings import IBM_AUTH_ENABLED

    if IBM_AUTH_ENABLED and jwt_token:
        headers.update(
            build_ibm_opensearch_vars(jwt_token, prefix="X-LANGFLOW-GLOBAL-VAR-")
        )

    # TODO: replace with dynamic user department/role from JWT/session
    headers["X-LANGFLOW-GLOBAL-VAR-DEPARTMENT_CONTEXT"] = os.getenv(
        "DEFAULT_DEPARTMENT_CONTEXT", "demo1"
    )
    headers["X-LANGFLOW-GLOBAL-VAR-ROLE_CONTEXT"] = os.getenv(
        "DEFAULT_ROLE_CONTEXT", "employee"
    )


async def build_mcp_global_vars_from_config(
    config,
    flows_service=None,
    jwt_token: str = None,
) -> Dict[str, str]:
    """Build MCP global variables dictionary from OpenRAG configuration."""
    global_vars = {}

    # Add OpenAI credentials
    if config.providers.openai.api_key:
        global_vars["OPENAI_API_KEY"] = config.providers.openai.api_key

    # Add Anthropic credentials
    if config.providers.anthropic.api_key:
        global_vars["ANTHROPIC_API_KEY"] = config.providers.anthropic.api_key

    # Add WatsonX credentials
    if config.providers.watsonx.api_key:
        global_vars["WATSONX_APIKEY"] = config.providers.watsonx.api_key

    if config.providers.watsonx.project_id:
        global_vars["WATSONX_PROJECT_ID"] = config.providers.watsonx.project_id

    # Add Ollama endpoint (with localhost transformation)
    if config.providers.ollama.endpoint:
        if flows_service:
            ollama_endpoint = await flows_service.resolve_ollama_url(
                config.providers.ollama.endpoint
            )
        else:
            ollama_endpoint = transform_localhost_url(config.providers.ollama.endpoint)
        global_vars["OLLAMA_BASE_URL"] = ollama_endpoint

    # Add selected embedding model
    if config.knowledge.embedding_model:
        global_vars["SELECTED_EMBEDDING_MODEL"] = config.knowledge.embedding_model

    # Inject OpenSearch URL so MCP servers always use the correct endpoint
    from config.settings import OPENSEARCH_HOST, OPENSEARCH_PORT

    global_vars["OPENSEARCH_URL"] = f"https://{OPENSEARCH_HOST}:{OPENSEARCH_PORT}"

    # VLM credentials
    vlm_endpoint = os.getenv("VLM_ENDPOINT")
    vlm_model = os.getenv("VLM_MODEL")
    vlm_api_key = os.getenv("VLM_API_KEY")
    if vlm_endpoint:
        global_vars["VLM_ENDPOINT"] = vlm_endpoint
    if vlm_model:
        global_vars["VLM_MODEL"] = vlm_model
    if vlm_api_key:
        global_vars["VLM_API_KEY"] = vlm_api_key

    # IBM mode: inject OpenSearch Basic credentials as separate global vars
    from config.settings import IBM_AUTH_ENABLED

    if IBM_AUTH_ENABLED and jwt_token:
        global_vars.update(build_ibm_opensearch_vars(jwt_token, prefix=""))

    # TODO: replace with dynamic user department/role from JWT/session
    global_vars["DEPARTMENT_CONTEXT"] = os.getenv("DEFAULT_DEPARTMENT_CONTEXT", "demo1")
    global_vars["ROLE_CONTEXT"] = os.getenv("DEFAULT_ROLE_CONTEXT", "employee")

    return global_vars
