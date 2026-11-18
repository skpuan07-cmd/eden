"""
AI Imagery controller — Use Case 4: Image Recognition (satellite/drone/field photos)

Upload an image and select an analysis type. The vision model will:
- flood_extent       — detect flood water boundaries
- building_damage   — classify building damage (pre/post event)
- road_passability   — detect blocked/impassable roads
- general            — general scene description + tag extraction

Endpoints:
- /eden/ai_imagery/                       → upload UI
- /eden/ai_imagery/analyze                → POST image, run analysis
- /eden/ai_imagery/jobs                   → admin: list all imagery jobs
- /eden/ai_imagery/job/<id>               → admin: view single job detail
"""
import json
import os
import tempfile
from s3.ai_client import AIClient, AIClientError


ANALYSIS_PROMPTS = {
    "flood_extent": """คุณคือผู้เชี่ยวชาญด้านการวิเคราะห์ภาพถ่ายดาวเทียมหลังเหตุการณ์อุทกภัย.
วิเคราะห์ภาพนี้แล้วส่งกลับเป็น JSON:
{
  "flood_detected": true/false,
  "estimated_flood_area_percent": 0-100,
  "affected_areas": ["รายชื่อพื้นที่ที่น้ำท่วม"],
  "water_bodies_visible": ["แม่น้ำ", "คลอง"],
  "priority_level": "high/medium/low",
  "recommendations": ["คำแนะนำเบื้องต้น"],
  "confidence": 0.0-1.0
}
""",
    "building_damage": """คุณคือผู้เชี่ยวชาญด้านการประเมินความเสียหายอาคารจากภาพถ่าย.
วิเคราะห์ภาพแล้วส่งกลับเป็น JSON:
{
  "buildings_visible": 0,
  "damaged_buildings": 0,
  "damage_levels": {
    "minor": 0,
    "moderate": 0,
    "severe": 0,
    "destroyed": 0
  },
  "estimated_affected_people": null,
  "priority_level": "high/medium/low",
  "observations": ["สิ่งที่เห็นในภาพ"],
  "confidence": 0.0-1.0
}
""",
    "road_passability": """คุณคือผู้เชี่ยวชาญด้านการวิเคราะห์ถนนจากภาพถ่าย.
วิเคราะห์ภาพแล้วส่งกลับเป็น JSON:
{
  "road_visible": true/false,
  "passable": true/false,
  "blockage_type": "none/debris/water/landslide/structure_damage/other",
  "estimated_blockage_length_m": null,
  "alternative_routes_visible": true/false,
  "priority_level": "high/medium/low",
  "observations": ["สิ่งที่เห็น"],
  "confidence": 0.0-1.0
}
""",
    "general": """วิเคราะห์ภาพนี้ในบริบทการจัดการภัยพิบัติ.
ส่งกลับเป็น JSON:
{
  "scene_description": "คำอธิบายภาพ",
  "incident_type": "ประเภทเหตุการณ์ที่เห็น",
  "people_visible": true/false,
  "estimated_people_count": 0,
  "visible_hazards": ["อันตรายที่เห็น"],
  "infrastructure_visible": ["สาธารณูปโภคที่เห็น"],
  "priority_level": "high/medium/low",
  "tags": ["tag1", "tag2"]
}
""",
}


def index():
    """Upload UI."""
    response.title = T("AI Imagery Analysis")
    return dict(analysis_types=list(ANALYSIS_PROMPTS.keys()))


def analyze():
    """POST: image + analysis_type → JSON result."""
    if request.env.request_method != "POST":
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "POST required"})

    analysis_type = request.post_vars.analysis_type
    if analysis_type not in ANALYSIS_PROMPTS:
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": f"unknown analysis_type: {analysis_type}"})

    upload = request.vars.file
    if not hasattr(upload, "file"):
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "no file uploaded"})

    # Save image temporarily
    ext = os.path.splitext(upload.filename)[1] or ".jpg"
    fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="imagery_")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(upload.file.read())
        upload.file.close()

        # Save copy in uploads/ for audit
        try:
            uploaded = db.ai_imagery_job.uploaded_file.store(
                upload.file, filename=upload.filename
            )
        except Exception:
            uploaded = None

        # Create job record
        job_id = db.ai_imagery_job.insert(
            user_id=auth.user.id if auth.user else None,
            uploaded_file=uploaded,
            imagery_type=request.post_vars.imagery_type or "field_photo",
            analysis_type=analysis_type,
            location_id=request.post_vars.location_id or None,
            status="processing",
        )
        db.commit()

        # Call vision model
        try:
            client = AIClient(timeout=120)
            prompt = ANALYSIS_PROMPTS[analysis_type]
            result = client.describe_image_json(tmp_path, prompt=prompt)
        except AIClientError as e:
            db.ai_imagery_job(job_id).update_record(status="failed")
            db.commit()
            response.headers["Content-Type"] = "application/json"
            return json.dumps({"error": str(e), "job_id": job_id})

        # Generate a short summary using the LLM (optional)
        summary = ""
        try:
            summary_resp = client.chat(
                json.dumps(result, ensure_ascii=False),
                system="สรุปผลการวิเคราะห์ภาพใน 2-3 ประโยคภาษาไทย"
            )
            summary = summary_resp.get("content", "")
        except Exception:
            pass

        # Update job
        db.ai_imagery_job(job_id).update_record(
            result_json=json.dumps(result, ensure_ascii=False),
            result_summary=summary,
            status="done",
            model="vision",
        )
        db.commit()

        response.headers["Content-Type"] = "application/json"
        return json.dumps({
            "job_id": job_id,
            "analysis_type": analysis_type,
            "result": result,
            "summary": summary,
        }, ensure_ascii=False)

    finally:
        try: os.unlink(tmp_path)
        except OSError: pass


def jobs():
    """Admin: list all imagery jobs."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user/login"))
    rows = db(db.ai_imagery_job.id > 0).select(
        orderby=~db.ai_imagery_job.created_on, limitby=(0, 50)
    )
    return dict(rows=rows)


def job():
    """Admin: view a single job."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user/login"))
    job_id = request.args(0)
    row = db.ai_imagery_job(job_id) or redirect(URL("ai_imagery", "jobs"))
    return dict(row=row)
