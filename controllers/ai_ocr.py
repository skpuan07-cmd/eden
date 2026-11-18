"""
AI OCR controller — Use Case 2: OCR + Data Extraction

Engine selection:
- "openthai" (default if IAPP_API_KEY is set) — uses OpenThai 2.1 from iApp
  Technology, which is purpose-built for Thai text (ID cards, receipts,
  general documents). Recommended for production use with Thai content.
- "vision_llm" (fallback) — uses the z-ai vision model (glm-5.3-flash).
  Works for any language but lower accuracy on Thai-specific formats.

Endpoints:
- /eden/ai_ocr/                → upload UI
- /eden/ai_ocr/extract         → POST image, returns JSON
- /eden/ai_ocr/engines         → GET, returns available engines
- /eden/ai_ocr/jobs            → admin: list OCR jobs
- /eden/ai_ocr/job/<id>        → admin: single job detail
"""
import json
import os
import tempfile


# Document-type → vision-LLM extraction prompt (used when engine="vision_llm"
# or when OpenThai is unavailable)
EXTRACTION_PROMPTS = {
    "id_card": """คุณคือระบบ OCR สำหรับบัตรประชาชนไทย.
ดึงข้อมูลจากรูปบัตรประชาชน แล้วส่งกลับเป็น JSON ที่มี field:
- first_name_th: ชื่อภาษาไทย
- last_name_th: นามสกุลภาษาไทย
- first_name_en: ชื่อภาษาอังกฤษ
- last_name_en: นามสกุลภาษาอังกฤษ
- id_number: เลขบัตรประชาชน 13 หลัก
- address: ที่อยู่ตามบัตร
- birth_date: วันเกิดในรูปแบบ YYYY-MM-DD (ถ้าเห็น)
- issue_date: วันออกบัตร (ถ้าเห็น)
- expiry_date: วันหมดอายุ (ถ้าเห็น)

กฎ:
- ถ้า field ใดไม่เห็นในรูป ให้ใส่ null
- อย่าคาดเดาข้อมูล
- ส่งกลับ JSON เท่านั้น (ไม่มี markdown, ไม่มีคำอธิบาย)
""",
    "invoice": """คุณคือระบบ OCR สำหรับใบเบิกวัสดุ/ใบสั่งซื้อ
ดึงข้อมูลจากรูป แล้วส่งกลับเป็น JSON ที่มี:
{
  "supplier_name": "ชื่อผู้จัดจำหน่าย",
  "invoice_number": "เลขที่ใบเบิก",
  "invoice_date": "YYYY-MM-DD",
  "items": [{"name": "ชื่อสินค้า", "quantity": 1, "unit": "หน่วย"}],
  "total_amount": 0.0,
  "currency": "THB"
}

กฎ: ถ้า field ใดไม่เห็น ใส่ null. ส่งกลับ JSON เท่านั้น.
""",
    "shelter_form": """คุณคือระบบ OCR สำหรับแบบฟอร์มลงทะเบียนศูนย์พักพิง
ดึงข้อมูลจากรูปแบบฟอร์ม แล้วส่งกลับเป็น JSON:
{
  "shelter_name": "ชื่อศูนย์พักพิง", "location": "ที่อยู่", "capacity": 0,
  "current_occupancy": 0, "contact_person": "ชื่อผู้ติดต่อ",
  "contact_phone": "เบอร์โทร", "facilities": ["water","electricity","first_aid"],
  "opened_date": "YYYY-MM-DD"
}
กฎ: ถ้า field ใดไม่เห็น ใส่ null. ส่งกลับ JSON เท่านั้น.
""",
    "victim_report": """คุณคือระบบ OCR สำหรับแบบฟอร์มรายงานผู้ประสบภัย
ดึงข้อมูลจากรูป แล้วส่งกลับเป็น JSON:
{
  "victim_name": "ชื่อผู้ประสบภัย", "victim_age": null, "victim_gender": null,
  "id_number": null, "family_members_count": null,
  "incident_location": "สถานที่เกิดเหตุ", "incident_date": "YYYY-MM-DD",
  "incident_type": "ประเภทภัย", "needs": ["food","shelter","medical"],
  "health_condition": "สภาพสุขภาพ",
  "reporter_name": "ชื่อผู้รายงาน", "reporter_phone": "เบอร์ผู้รายงาน"
}
กฎ: ถ้า field ใดไม่เห็น ใส่ null. ข้อมูลนี้ sensitive — ห้ามเปิดเผยในคำตอบนอกจาก JSON. ส่งกลับ JSON เท่านั้น.
""",
}


def index():
    """Upload UI."""
    response.title = T("AI OCR — Document Extraction")

    # Detect available engines
    openthai_available = False
    try:
        from s3.ai_ocr_openthai import OpenThaiClient
        openthai_available = OpenThaiClient.is_available()
    except ImportError:
        pass

    default_engine = "openthai" if openthai_available else "vision_llm"

    return dict(
        document_types=list(EXTRACTION_PROMPTS.keys()),
        openthai_available=openthai_available,
        default_engine=default_engine,
    )


def engines():
    """Return available OCR engines as JSON."""
    openthai_available = False
    try:
        from s3.ai_ocr_openthai import OpenThaiClient
        openthai_available = OpenThaiClient.is_available()
    except ImportError:
        pass
    response.headers["Content-Type"] = "application/json"
    return json.dumps({
        "openthai": {"available": openthai_available, "label": "OpenThai 2.1 (iApp)"},
        "vision_llm": {"available": True, "label": "Vision LLM (glm-5.3-flash fallback)"},
        "default": "openthai" if openthai_available else "vision_llm",
    })


def extract():
    """POST: receive image + document_type, run OCR, return extracted JSON."""
    if request.env.request_method != "POST":
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "POST required"})

    doc_type = request.post_vars.document_type
    if doc_type not in EXTRACTION_PROMPTS:
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": f"unknown document_type: {doc_type}"})

    upload = request.vars.file
    if not hasattr(upload, "file"):
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "no file uploaded"})

    # PDPA consent check
    consent = request.post_vars.consent
    if consent != "yes":
        response.headers["Content-Type"] = "application/json"
        return json.dumps({
            "error": "consent_required",
            "message": "การประมวลผลรูปเอกสารที่มีข้อมูลส่วนบุคคลต้องได้รับความยินยอม (PDPA)",
        })

    # Engine selection: "auto" (default) | "openthai" | "vision_llm"
    requested_engine = (request.post_vars.engine or "auto").lower()
    openthai_available = False
    try:
        from s3.ai_ocr_openthai import OpenThaiClient
        openthai_available = OpenThaiClient.is_available()
    except ImportError:
        pass

    if requested_engine == "auto":
        engine = "openthai" if openthai_available else "vision_llm"
    elif requested_engine == "openthai":
        if not openthai_available:
            response.headers["Content-Type"] = "application/json"
            return json.dumps({
                "error": "OpenThai engine requested but IAPP_API_KEY not set. "
                         "Set the env var or use engine=vision_llm.",
            })
        engine = "openthai"
    else:
        engine = "vision_llm"

    # Save uploaded image to a temp file
    ext = os.path.splitext(upload.filename)[1] or ".jpg"
    fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="ocr_")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(upload.file.read())
        upload.file.close()

        # Save a copy in Eden uploads/ for audit trail
        try:
            uploaded = db.ai_ocr_job.upload.store(upload.file, filename=upload.filename)
        except Exception:
            uploaded = None

        # Log the job
        job_id = db.ai_ocr_job.insert(
            user_id=auth.user.id if auth.user else None,
            document_type=doc_type,
            uploaded_file=uploaded,
            target_table=request.post_vars.target_table,
            status="processing",
            consent_given=True,
            ip=request.env.remote_addr,
        )
        db.commit()

        # --- OCR engine dispatch ---
        # Strategy:
        # - If engine == "openthai" or "auto" with OpenThai available:
        #     try OpenThai first; if it returns "unsupported doc type" or
        #     "NO_ID_CARD_FOUND" (image isn't a real ID card), fall back to
        #     vision LLM automatically.
        # - If engine == "vision_llm": use vision LLM directly.
        openthai_attempted = False
        openthai_failed = False

        if engine == "openthai" or (engine == "auto" and False):  # 'auto' handled above
            openthai_attempted = True
            extracted, engine_detail = _extract_with_openthai(doc_type, tmp_path)
            # Check for known failure modes that should trigger fallback
            if isinstance(extracted, dict):
                err_msg = (extracted.get("error") or "").lower()
                unsupported = extracted.get("supported") is False
                no_id = "no_id_card_found" in err_msg
                if unsupported or no_id or "openthai_failed" in (engine_detail or ""):
                    openthai_failed = True
        elif engine == "auto":  # OpenThai is available and was selected
            openthai_attempted = True
            extracted, engine_detail = _extract_with_openthai(doc_type, tmp_path)
            if isinstance(extracted, dict):
                err_msg = (extracted.get("error") or "").lower()
                unsupported = extracted.get("supported") is False
                no_id = "no_id_card_found" in err_msg
                if unsupported or no_id or "openthai_failed" in (engine_detail or ""):
                    openthai_failed = True

        # Fallback path: vision LLM
        if engine == "vision_llm" or openthai_failed:
            extracted, engine_detail = _extract_with_vision_llm(doc_type, tmp_path)
            if openthai_attempted and openthai_failed:
                # Annotate that we fell back
                engine_detail = "openthai_fallback_to_vision_llm"

        if isinstance(extracted, dict) and "error" in extracted:
            db.ai_ocr_job(job_id).update_record(
                status="failed", error_message=str(extracted["error"])
            )
            db.commit()
            response.headers["Content-Type"] = "application/json"
            return json.dumps({"error": extracted["error"], "job_id": job_id, "engine": engine_detail})

        # If we used OpenThai general OCR for non-ID documents, run the LLM
        # afterwards to structure the raw text into JSON.
        if engine == "openthai" and doc_type != "id_card" and "text" in extracted:
            structured = _structure_with_llm(doc_type, extracted["text"])
            if structured and "error" not in structured:
                extracted = structured

        # Update job record
        db.ai_ocr_job(job_id).update_record(
            extracted_data=json.dumps(extracted, ensure_ascii=False),
            status="done",
            model=engine_detail,
        )
        db.commit()

        response.headers["Content-Type"] = "application/json"
        return json.dumps({
            "job_id": job_id,
            "document_type": doc_type,
            "engine": engine_detail,
            "extracted_data": extracted,
            "openthai_attempted": openthai_attempted,
            "openthai_failed": openthai_failed,
        }, ensure_ascii=False)

    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# -------------------------------------------------------------------------
# Engine 1: OpenThai 2.1
# -------------------------------------------------------------------------
def _extract_with_openthai(doc_type, image_path):
    """Run OCR via the OpenThai 2.1 API.

    Returns (extracted_dict, engine_label).
    For id_card: returns structured fields directly.
    For other doc types: returns raw Thai text for LLM structuring.
    """
    from s3.ai_ocr_openthai import OpenThaiClient, OpenThaiError
    try:
        client = OpenThaiClient(timeout=60)
        result = client.recognize(doc_type, image_path)
        engine_label = result.pop("engine", "openthai")
        # For id_card, the result has all the structured fields already
        if doc_type == "id_card":
            # Drop the "raw" sub-dict before returning to client (it's huge)
            result.pop("raw", None)
            return result, engine_label
        # For other types, we have "text" — return it for LLM structuring
        return result, engine_label
    except OpenThaiError as e:
        return {"error": f"OpenThai: {e}"}, "openthai_failed"
    except Exception as e:
        return {"error": f"OpenThai unexpected error: {e}"}, "openthai_failed"


# -------------------------------------------------------------------------
# Engine 2: Vision LLM fallback (glm-5.3-flash via z-ai CLI)
# -------------------------------------------------------------------------
def _extract_with_vision_llm(doc_type, image_path):
    """Run OCR using the z-ai vision model."""
    from s3.ai_client import AIClient, AIClientError
    try:
        client = AIClient(timeout=120)
        prompt = EXTRACTION_PROMPTS[doc_type]
        result = client.describe_image_json(image_path, prompt=prompt)
        return result, "vision_llm"
    except AIClientError as e:
        return {"error": str(e)}, "vision_llm_failed"
    except Exception as e:
        return {"error": f"Vision LLM unexpected error: {e}"}, "vision_llm_failed"


# -------------------------------------------------------------------------
# Helper: structure raw Thai text via LLM (used after OpenThai general OCR)
# -------------------------------------------------------------------------
def _structure_with_llm(doc_type, raw_text):
    """Send raw Thai OCR text to the LLM and ask it to produce structured JSON."""
    if not raw_text:
        return None
    from s3.ai_client import AIClient, AIClientError
    prompt = EXTRACTION_PROMPTS[doc_type] + "\n\nข้อความ OCR ที่ดึงได้:\n" + raw_text[:3000]
    try:
        client = AIClient(timeout=60)
        return client.chat_json(prompt)
    except AIClientError:
        return None


# -------------------------------------------------------------------------
# Admin views
# -------------------------------------------------------------------------
def jobs():
    """Admin: list OCR jobs (most recent first)."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user_login"))
    rows = db(db.ai_ocr_job.id > 0).select(
        orderby=~db.ai_ocr_job.created_on, limitby=(0, 100)
    )
    return dict(rows=rows)


def job():
    """Admin: view a single job detail."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user_login"))
    job_id = request.args(0)
    row = db.ai_ocr_job(job_id) or redirect(URL("ai_ocr", "jobs"))
    return dict(row=row)
