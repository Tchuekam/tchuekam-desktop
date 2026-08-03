"""
Input sanitization and security utilities against XSS and injection attacks.
"""

import html
import re
from typing import Any, Dict, List, Union


class XSSSanitizer:
    """Sanitizes user text inputs to neutralize dangerous HTML/script tags."""

    # Patterns targeting script tags, inline event handlers, and dangerous URIs
    SCRIPT_PATTERN = re.compile(r"<script.*?>.*?</script>", re.IGNORECASE | re.DOTALL)
    EVENT_HANDLER_PATTERN = re.compile(r"on\w+\s*=\s*[\"'].*?[\"']", re.IGNORECASE)
    JAVASCRIPT_URI_PATTERN = re.compile(r"javascript:\s*", re.IGNORECASE)
    HTML_TAG_PATTERN = re.compile(r"<[^>]+>", re.IGNORECASE)

    @classmethod
    def sanitize_string(cls, value: str, allow_html: bool = False) -> str:
        """Sanitizes a string value.

        If allow_html is False, strips all HTML tags and escapes HTML entities.
        If allow_html is True, strips script tags and event handlers.
        """
        if not isinstance(value, str):
            return value

        # Strip script tags & javascript URIs
        cleaned = cls.SCRIPT_PATTERN.sub("", value)
        cleaned = cls.JAVASCRIPT_URI_PATTERN.sub("", cleaned)
        cleaned = cls.EVENT_HANDLER_PATTERN.sub("", cleaned)

        if not allow_html:
            cleaned = cls.HTML_TAG_PATTERN.sub("", cleaned)
            cleaned = html.escape(cleaned, quote=False)

        return cleaned.strip()

    @classmethod
    def sanitize_data(cls, data: Union[Dict, List, str, Any]) -> Any:
        """Recursively sanitizes nested dictionaries, lists, and strings."""
        if isinstance(data, str):
            return cls.sanitize_string(data)
        elif isinstance(data, dict):
            return {k: cls.sanitize_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [cls.sanitize_data(item) for item in data]
        return data
