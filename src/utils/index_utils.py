"""Utilities for resolving dynamic OpenSearch index names."""

import re
from typing import Optional


def normalize_index_name(name: str) -> str:
    """Normalize a string to a valid OpenSearch index name.

    Rules:
    - Lowercase
    - Replace spaces and invalid chars with underscores
    - Strip leading/trailing underscores/hyphens
    - Must not start with _ or -
    """
    name = name.lower().strip()
    # Replace any character that is not alphanumeric, hyphen, or underscore
    name = re.sub(r"[^a-z0-9_\-]", "_", name)
    # Collapse multiple underscores/hyphens
    name = re.sub(r"[_\-]{2,}", "_", name)
    name = name.strip("_-")
    return name


def resolve_index_name(
    department: Optional[str],
    user_id: Optional[str],
    fallback_index: str,
) -> str:
    """Resolve the target OpenSearch index name for an ingest request.

    Priority:
    1. department (non-empty) => normalize(department)
    2. no department + user_id  => "personal_" + normalize(user_id)
    3. fallback                 => fallback_index (OPENSEARCH_INDEX_NAME)

    Raises:
        ValueError: if department is absent AND user_id is also absent/empty,
                    meaning we cannot determine a personal index.
    """
    dept = (department or "").strip()
    uid = (user_id or "").strip()

    if dept:
        return normalize_index_name(dept)

    if uid:
        return "personal_" + normalize_index_name(uid)

    # Neither department nor user_id — cannot resolve personal index
    raise ValueError(
        "Cannot resolve index: 'department' is empty and 'user_id' is missing. "
        "Provide a department or ensure the request is authenticated."
    )
