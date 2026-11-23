"""Settings, read from .env locally or from Streamlit secrets when hosted."""

import os

from dotenv import load_dotenv

load_dotenv()


def get_setting(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        try:
            import streamlit as st

            value = st.secrets.get(name)
        except Exception:  # no secrets file, or not running in Streamlit
            value = None
    return str(value).strip() if value is not None else default


def get_int(name: str, default: int) -> int:
    try:
        return int(get_setting(name, str(default)))
    except ValueError:
        return default


def get_bool(name: str, default: bool = False) -> bool:
    return get_setting(name, str(default)).lower() in ("1", "true", "yes", "on")
