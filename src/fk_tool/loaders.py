"""
Data loaders for sign data.

Supports JSON file loading, MongoDB loading, and AI output loading.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def load_from_json(filepath: str) -> list[dict]:
    """Load sign data from a JSON file.

    Supports two formats:
      - Array of sign objects: [{"token": "HELLO", ...}, ...]
      - Object keyed by token: {"HELLO": {"keyframes": [...]}, ...}

    In the keyed-object format, the token key is injected into each sign dict
    as the "token" field if not already present.

    Args:
        filepath: Path to the JSON file.

    Returns:
        List of raw sign dictionaries.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
        ValueError: If the top-level structure is not a list or dict.
    """
    path = Path(filepath)
    with path.open("r", encoding="utf-8") as file_handle:
        data = json.load(file_handle)

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        return _expand_keyed_signs(data)

    raise ValueError(
        f"Expected JSON array or object at top level, got {type(data).__name__}"
    )


def load_from_mongodb(
    uri: str | None = None,
    db_name: str | None = None,
    collection_name: str = "signs",
    tokens: list[str] | None = None,
) -> list[dict]:
    """Load sign data directly from MongoDB.

    Uses the same connection config as the main ASL Robot app. If uri or db_name
    is None, reads from .env using python-dotenv (MONGODB_URI, MONGODB_DB_NAME).

    Args:
        uri: MongoDB connection URI, or None to read from .env.
        db_name: Database name, or None to read from .env.
        collection_name: Collection to query (default "signs").
        tokens: If provided, filter to only these token names.

    Returns:
        List of raw sign dictionaries.

    Raises:
        ConnectionError: If MongoDB is unreachable or misconfigured.
        ImportError: If pymongo is not installed.
    """
    try:
        from pymongo import MongoClient
    except ImportError:
        raise ImportError(
            "pymongo is required for MongoDB loading. "
            "Install it with: pip install pymongo"
        )

    resolved_uri, resolved_db = _resolve_mongodb_config(uri, db_name)

    try:
        client = MongoClient(resolved_uri, serverSelectionTimeoutMS=5000)
        database = client[resolved_db]
        collection = database[collection_name]

        query = _build_token_query(tokens)
        documents = list(collection.find(query, {"_id": 0}))

        client.close()
    except Exception as error:
        raise ConnectionError(
            f"Failed to connect to MongoDB. Check your .env file and connection.\n"
            f"URI: {resolved_uri[:30]}...\n"
            f"DB: {resolved_db}\n"
            f"Error: {error}"
        ) from error

    return documents


def load_from_ai_output(filepath: str) -> list[dict]:
    """Load AI-generated motion scripts from a JSON file.

    Wraps load_from_json and tags each sign with a metadata source marker
    so reports can distinguish AI-generated from database signs.

    Args:
        filepath: Path to the AI output JSON file.

    Returns:
        List of raw sign dicts, each with "_source": "ai_generated" added.
    """
    signs = load_from_json(filepath)
    for sign in signs:
        sign["_source"] = "ai_generated"
    return signs


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _expand_keyed_signs(keyed_data: dict) -> list[dict]:
    """Convert a token-keyed dict into a list of sign dicts.

    Args:
        keyed_data: Dict mapping token strings to sign data dicts.

    Returns:
        List of sign dicts, each with a "token" field.
    """
    signs: list[dict] = []
    for token, sign_data in keyed_data.items():
        if isinstance(sign_data, dict):
            if "token" not in sign_data:
                sign_data["token"] = token
            signs.append(sign_data)
        else:
            signs.append({"token": token, "data": sign_data})
    return signs


def _resolve_mongodb_config(
    uri: str | None,
    db_name: str | None,
) -> tuple[str, str]:
    """Resolve MongoDB URI and DB name, falling back to .env.

    Args:
        uri: Explicit URI or None.
        db_name: Explicit DB name or None.

    Returns:
        Tuple of (resolved_uri, resolved_db_name).

    Raises:
        ConnectionError: If required values can't be resolved.
    """
    if uri is None or db_name is None:
        _load_dotenv_if_available()

    resolved_uri = uri or os.getenv("MONGODB_URI")
    resolved_db = db_name or os.getenv("MONGODB_DB_NAME")

    if not resolved_uri:
        raise ConnectionError(
            "MongoDB URI not provided and MONGODB_URI not found in .env. "
            "Set MONGODB_URI in your .env file or pass uri= explicitly."
        )
    if not resolved_db:
        raise ConnectionError(
            "MongoDB DB name not provided and MONGODB_DB_NAME not found in .env. "
            "Set MONGODB_DB_NAME in your .env file or pass db_name= explicitly."
        )

    return resolved_uri, resolved_db


def _load_dotenv_if_available() -> None:
    """Load .env file if python-dotenv is installed."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def _build_token_query(tokens: list[str] | None) -> dict:
    """Build a MongoDB query filter for token names.

    Args:
        tokens: List of token names to filter by, or None for all.

    Returns:
        MongoDB query dict.
    """
    if tokens is None:
        return {}
    return {"token": {"$in": [t.upper() for t in tokens]}}
