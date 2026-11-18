"""
OpenThai 2.1 OCR client — Thai-specific OCR by iApp Technology Co., Ltd.

OpenThai 2.1 is a Thai-tuned OCR model with dedicated endpoints for:
- Thai national ID card (returns structured fields)
- General Thai text (printed/handwritten)
- Receipts / invoices

API docs: https://api.iapp.co.th/
Requires an API key from iApp (https://iapp.co.th/) — set via env var IAPP_API_KEY.

If IAPP_API_KEY is not set, AIClient.describe_image (vision LLM) should be
used as a fallback instead.
"""
import os
import json
import requests


IAPP_BASE_URL = "https://api.iapp.co.th"

# Document-type → OpenThai endpoint mapping.
# Confirmed working endpoints (verified against iApp docs Jan 2025):
#   - Thai ID card: POST /thai-national-id-card/v3.5/front
#     (returns structured fields directly: title, first_name_th, last_name_th,
#      first_name_en, last_name_en, id_card_number, address, birth_date, etc.)
# General Thai OCR endpoints (OpenThai 2.1 OCR Text / Markdown) exist as
# services but their exact URL paths are not publicly documented.
# Until we can confirm those, non-ID-card documents fall back to vision LLM.
OPENTHAI_ENDPOINTS = {
    "id_card": "/thai-national-id-card/v3.5/front",
    # Other doc types → not supported by OpenThai public endpoints yet;
    # controller will route them to vision LLM automatically.
}


class OpenThaiError(Exception):
    """Raised when the OpenThai API call fails."""
    pass


class OpenThaiClient:
    """Thin Python wrapper around the iApp OpenThai 2.1 OCR API."""

    def __init__(self, api_key=None, base_url=None, timeout=60):
        self.api_key = api_key or os.environ.get("IAPP_API_KEY") or os.environ.get("OPENTHAI_API_KEY")
        if not self.api_key:
            raise OpenThaiError(
                "IAPP_API_KEY environment variable not set. "
                "Get one at https://iapp.co.th/ and export IAPP_API_KEY=..."
            )
        self.base_url = base_url or IAPP_BASE_URL
        self.timeout = timeout

    @classmethod
    def is_available(cls):
        """Check if OpenThai can be used (i.e., API key is set)."""
        return bool(os.environ.get("IAPP_API_KEY") or os.environ.get("OPENTHAI_API_KEY"))

    def _post_file(self, endpoint, file_path, extra_fields=None):
        """POST a file to the given OpenThai endpoint."""
        url = self.base_url + endpoint
        headers = {"apikey": self.api_key}
        try:
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f, "image/jpeg")}
                resp = requests.post(
                    url,
                    headers=headers,
                    files=files,
                    data=extra_fields or {},
                    timeout=self.timeout,
                )
        except requests.RequestException as e:
            raise OpenThaiError(f"HTTP request failed: {e}")
        if resp.status_code != 200:
            raise OpenThaiError(
                f"OpenThai API returned HTTP {resp.status_code}: {resp.text[:300]}"
            )
        try:
            return resp.json()
        except ValueError:
            raise OpenThaiError(f"OpenThai response not JSON: {resp.text[:300]}")

    # -----------------------------------------------------------------
    # Thai National ID Card
    # -----------------------------------------------------------------
    def recognize_id_card(self, image_path):
        """Recognize a Thai national ID card image.

        Returns a dict with normalized fields:
            first_name_th, last_name_th, first_name_en, last_name_en,
            id_number, address, birth_date, issue_date, expiry_date,
            raw (the original API response)
        """
        data = self._post_file(OPENTHAI_ENDPOINTS["id_card"], image_path)
        # The OpenThai v2 response uses a 'data' wrapper or returns fields directly.
        # Handle both shapes defensively.
        raw = data
        d = data.get("data", data) if isinstance(data, dict) else {}
        # Common field names used by iApp's ID card endpoint
        return {
            "first_name_th": d.get("first_name_th") or d.get("th_first_name"),
            "last_name_th": d.get("last_name_th") or d.get("th_last_name"),
            "first_name_en": d.get("first_name_en") or d.get("en_first_name"),
            "last_name_en": d.get("last_name_en") or d.get("en_last_name"),
            "id_number": d.get("id_card_number") or d.get("id_number") or d.get("citizen_id"),
            "address": d.get("address") or d.get("th_address"),
            "birth_date": d.get("birth_date") or d.get("birthday") or d.get("date_of_birth"),
            "issue_date": d.get("issue_date") or d.get("date_of_issue"),
            "expiry_date": d.get("expiry_date") or d.get("date_of_expiry"),
            "religion": d.get("religion"),
            "raw": raw,
        }

    # -----------------------------------------------------------------
    # General Thai OCR
    # -----------------------------------------------------------------
    def recognize_general(self, image_path):
        """Recognize general Thai text in an image.

        Returns a dict: {text, raw}
        """
        data = self._post_file(OPENTHAI_ENDPOINTS["general"], image_path)
        # Response shape varies; try common keys
        text = ""
        if isinstance(data, dict):
            text = data.get("text") or data.get("raw_text") or data.get("content") or ""
            if not text and "data" in data:
                inner = data["data"]
                if isinstance(inner, str):
                    text = inner
                elif isinstance(inner, dict):
                    text = inner.get("text") or inner.get("raw_text") or ""
                elif isinstance(inner, list):
                    text = "\n".join(str(x) for x in inner)
        return {"text": text, "raw": data}

    # -----------------------------------------------------------------
    # Dispatch by document type
    # -----------------------------------------------------------------
    def recognize(self, document_type, image_path):
        """Run OCR for the given document_type.

        Returns dict: {engine, ...fields} for id_card, or
                      {engine, supported: False} for unsupported doc types
                      (caller should fall back to vision LLM).
        """
        if document_type not in OPENTHAI_ENDPOINTS:
            return {"engine": "openthai_unsupported", "supported": False,
                    "message": f"OpenThai has no public endpoint for document_type='{document_type}'. "
                               f"Use engine=vision_llm for this document type."}
        if document_type == "id_card":
            return {"engine": "openthai_id_card", **self.recognize_id_card(image_path)}
        # (reserved for future endpoints)
        return {"engine": "openthai_unsupported", "supported": False}
