"""
AI Query controller — Use Case 6: Natural Language Query

Allow admin users to ask questions in plain Thai/English:
"แสดงศูนย์พักพิงในเชียงรายที่รองรับได้มากกว่า 100 คน"

The LLM converts this into an Eden REST API URL → the controller executes
the URL internally → returns JSON → the LLM formats the result as Thai.

Endpoints:
- /eden/ai_query/                → query UI (admin only)
- /eden/ai_query/ask             → POST: question → answer (JSON)
- /eden/ai_query/history         → user's query history
"""
import json
import time
from s3.ai_client import AIClient, AIClientError


# Allowed Eden controllers for NLQ (whitelist — PDPA safety)
ALLOWED_CONTROLLERS = {
    "org": ["organisation", "office", "site"],
    "cr": ["shelter"],
    "inv": ["warehouse", "inv_item"],
    "project": ["project"],
    "cms": ["post"],
    "gis": ["location"],
    "hrm": ["human_resource"],
    "req": ["req"],
    "stats": ["index"],
}


def index():
    """Query UI (admin only)."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user_login"))
    response.title = T("Natural Language Query")
    return dict()


def ask():
    """POST: question → answer."""
    if not auth.s3_has_role("ADMIN"):
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "admin required"})
    if request.env.request_method != "POST":
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "POST required"})

    question = (request.post_vars.question or "").strip()
    if not question:
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "missing question"})

    t0 = time.time()
    log_id = db.ai_query_log.insert(
        user_id=auth.user.id,
        question=question,
        ip=request.env.remote_addr,
    )
    db.commit()

    # Build the function-calling prompt
    schema_desc = "\n".join(
        f"- /eden/{ctrl}/<function> (allowed functions: {', '.join(fns)})"
        for ctrl, fns in ALLOWED_CONTROLLERS.items()
    )
    prompt = f"""แปลงคำถามเป็น Eden REST API URL (relative path).

ระบบ Sahana Eden มี controllers และ functions ที่อนุญาต:
{schema_desc}

กฎ:
- URL ต้องขึ้นต้นด้วย /eden/<controller>/<function>.json
- ใช้ query parameters สำหรับ filter: ?<field>__<op>=<value>
  - ตัวอย่าง: ?capacity__gt=100&location.name__like=เชียงราย
  - operators: __gt, __gte, __lt, __lte, __eq, __like, __in
- จำกัดผลลัพธ์: เพิ่ม &limit=20 (default 20)
- ห้ามเข้าถึงข้อมูล sensitive (auth_user, dvr_case, med_patient, msg_log)
- ส่งกลับเฉพาะ URL บรรทัดเดียว ไม่มีคำอธิบาย ไม่มี markdown

ตัวอย่าง:
- คำถาม: "แสดงศูนย์พักพิงในเชียงรายที่รองรับได้มากกว่า 100 คน"
- ตอบ: /eden/cr/shelter.json?capacity__gt=100&location.name__like=เชียงราย&limit=20

คำถามที่ต้องตอบ: {question}
"""

    try:
        client = AIClient(timeout=60)
        result = client.chat(prompt)
    except AIClientError as e:
        db.ai_query_log(log_id).update_record(
            error_message=str(e) if hasattr(db.ai_query_log, "error_message") else None,
        )
        db.commit()
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": str(e)})

    api_url = result.get("content", "").strip()
    # Strip markdown code fences if present
    if api_url.startswith("```"):
        lines = api_url.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        api_url = "\n".join(lines).strip()
    # Take only the first non-empty line, strip quotes
    api_url = next((line.strip().strip('"').strip("'") for line in api_url.splitlines() if line.strip()), "")
    # Safety: only allow whitelisted controllers
    if not api_url or not _is_safe_url(api_url):
        db.ai_query_log(log_id).update_record(
            interpreted_query=api_url or "(empty)",
            executed=False,
            answer_text="Refused: URL not in whitelist or empty",
        )
        db.commit()
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "generated URL not allowed", "url": api_url, "raw": result.get("content", "")[:500]})

    # Execute the query directly against the DB (avoids HTTP self-call deadlock)
    parsed = _execute_query_via_db(api_url)
    if "error" in parsed:
        db.ai_query_log(log_id).update_record(
            interpreted_query=api_url,
            executed=False,
            answer_text=f"DB error: {parsed['error']}",
            latency_ms=int((time.time() - t0) * 1000),
        )
        db.commit()
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": parsed["error"], "url": api_url})

    records = parsed.get("_results", [])
    count = len(records)

    # Format the answer with LLM
    summary_prompt = f"""คำถาม: {question}
URL ที่ query: {api_url}
จำนวนผลลัพธ์: {count}
ข้อมูล (ส่วนตัวอย่าง 5 records): {json.dumps(records[:5], ensure_ascii=False) if isinstance(records, list) else str(records)[:1500]}

จงสรุปคำตอบเป็นภาษาไทยกระชับ ไม่เกิน 200 คำ ระบุ:
- จำนวนรายการที่พบ
- ตัวอย่าง 5 รายการแรก (ถ้าเกี่ยวข้อง)
- คำแนะนำถ้ามี
"""
    try:
        summary = client.chat(summary_prompt).get("content", "")
    except Exception:
        summary = f"พบ {count} รายการจาก query"

    db.ai_query_log(log_id).update_record(
        interpreted_query=api_url,
        executed=True,
        result_count=count,
        answer_text=summary,
        model=result.get("model"),
        latency_ms=int((time.time() - t0) * 1000),
    )
    db.commit()

    response.headers["Content-Type"] = "application/json"
    return json.dumps({
        "answer": summary,
        "api_url": api_url,
        "count": count,
        "sample": records[:5] if isinstance(records, list) else records,
        "log_id": log_id,
    }, ensure_ascii=False)


def history():
    """Show user's query history."""
    if not auth.user:
        redirect(URL("default", "user_login"))
    rows = db(db.ai_query_log.user_id == auth.user.id).select(
        orderby=~db.ai_query_log.created_on, limitby=(0, 30)
    )
    return dict(rows=rows)


def _is_safe_url(url):
    """Verify the URL is in the whitelist of allowed controllers."""
    if not url.startswith("/eden/"):
        return False
    parts = url[len("/eden/"):].split("/")
    if len(parts) < 2:
        return False
    ctrl = parts[0]
    fn = parts[1].split(".")[0].split("?")[0]
    if ctrl not in ALLOWED_CONTROLLERS:
        return False
    if fn not in ALLOWED_CONTROLLERS[ctrl]:
        return False
    return True


# -------------------------------------------------------------------------
# Mapping: controller.function → Eden DB table (always-loaded tables only)
# -------------------------------------------------------------------------
_TABLE_MAP = {
    ("org", "organisation"): "org_organisation",
    ("org", "office"): "org_office",
    ("org", "site"): "org_site",
    ("cr", "shelter"): "cr_shelter",
    ("inv", "warehouse"): "inv_warehouse",
    ("inv", "inv_item"): "inv_inv_item",
    ("project", "project"): "project_project",
    ("cms", "post"): "cms_post",
    ("gis", "location"): "gis_location",
    ("hrm", "human_resource"): "hrm_human_resource",
    ("req", "req"): "req_req",
}


def _execute_query_via_db(api_url):
    """Parse the generated URL and execute it directly via PyDAL.

    Avoids the HTTP self-call deadlock by querying the database directly.
    Returns dict: {"_results": [list of dicts], "_count": int} or {"error": str}
    """
    import urllib.parse as up
    # Parse URL: /eden/<ctrl>/<fn>.json?<query>
    if not api_url.startswith("/eden/"):
        return {"error": f"URL doesn't start with /eden/: {api_url}"}
    path_query = api_url[len("/eden/"):]
    if "?" in path_query:
        path, query_string = path_query.split("?", 1)
    else:
        path, query_string = path_query, ""
    parts = path.split("/")
    if len(parts) < 2:
        return {"error": "URL path too short"}
    ctrl = parts[0]
    fn = parts[1].split(".")[0]  # strip .json
    key = (ctrl, fn)
    if key not in _TABLE_MAP:
        return {"error": f"no table mapping for {key}"}
    table_name = _TABLE_MAP[key]

    # Eden uses lazy table loading — try to access via s3db first
    try:
        from gluon import current
        s3db = current.s3db
        # This triggers lazy loading
        table = getattr(s3db, table_name)
    except Exception:
        # Fall back to db.<table> if it's already loaded
        table = getattr(db, table_name, None)
        if table is None:
            return {"error": f"table {table_name} not loaded"}

    # Parse query string into filters
    params = up.parse_qs(query_string)
    limit = int(params.get("limit", ["20"])[0])
    query = (table.deleted != True) if "deleted" in table.fields else (table.id > 0)

    # Apply simple filters: <field>__<op>=<value>
    OPS = {
        "gt": lambda f, v: f > _coerce(v),
        "gte": lambda f, v: f >= _coerce(v),
        "lt": lambda f, v: f < _coerce(v),
        "lte": lambda f, v: f <= _coerce(v),
        "eq": lambda f, v: f == v,
        "like": lambda f, v: f.contains(v.replace("%", "")),
        "in": lambda f, v: f.belongs(v.split(",")),
    }
    for raw_key, raw_values in params.items():
        if raw_key in ("limit", "orderby", "page", "format"):
            continue
        value = raw_values[0]
        if "__" in raw_key:
            field_name, op_name = raw_key.rsplit("__", 1)
        else:
            field_name, op_name = raw_key, "eq"
        # field_name may be "location.name" — skip cross-table for now
        if "." in field_name:
            continue
        field = getattr(table, field_name, None)
        if field is None:
            continue
        op = OPS.get(op_name)
        if op is None:
            continue
        try:
            query = query & op(field, value)
        except Exception:
            continue

    # Execute
    try:
        rows = db(query).select(limitby=(0, limit))
    except Exception as e:
        return {"error": f"query failed: {e}"}

    # Convert rows to plain dicts
    results = []
    for r in rows:
        try:
            d = r.as_dict()
            # Strip large/binary fields
            for k in list(d.keys()):
                v = d[k]
                if isinstance(v, str) and len(v) > 200:
                    d[k] = v[:200] + "..."
            results.append(d)
        except Exception:
            continue
    return {"_results": results, "_count": len(results)}


def _coerce(value):
    """Try to convert a string to int/float for numeric comparisons."""
    try:
        if "." in value:
            return float(value)
        return int(value)
    except (ValueError, TypeError):
        return value
