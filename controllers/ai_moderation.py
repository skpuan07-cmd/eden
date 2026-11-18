"""
AI Content Moderation controller — Use Case 10: Auto-moderate user-submitted content

Hooks into:
- cms_post (CMS posts)
- msg_log (SMS/email logs - optionally)
- ai_chat_log (chatbot conversations)

Workflow:
1. When a user submits a CMS post, an automation creates a moderation job
   BEFORE the post is published.
2. The LLM scores the content across categories: hate, harassment, self-harm,
   sexual, violence, spam, pdpa_violation (mentions of personal IDs).
3. Auto-actions: high-severity → blocked; medium → flagged for review;
   low → published.
4. Admins can review flagged items at /eden/ai_moderation/queue

Endpoints:
- /eden/ai_moderation/                → admin dashboard
- /eden/ai_moderation/queue           → pending review queue
- /eden/ai_moderation/check           → POST: text → moderation result
- /eden/ai_moderation/approve/<id>    → approve a flagged item
- /eden/ai_moderation/reject/<id>     → reject (and block source content)
- /eden/ai_moderation/history         → moderation log
"""
import json
import re
from s3.ai_client import AIClient, AIClientError


def index():
    """Admin dashboard."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user_login"))
    pending = db(db.ai_moderation_queue.action == "pending").count()
    approved = db(db.ai_moderation_queue.action == "approved").count()
    rejected = db(db.ai_moderation_queue.action == "rejected").count()
    blocked = db(db.ai_moderation_queue.auto_action == "blocked").count()
    response.title = T("AI Content Moderation")
    return dict(pending=pending, approved=approved, rejected=rejected, blocked=blocked)


def queue():
    """Pending moderation queue."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user_login"))
    rows = db(db.ai_moderation_queue.action == "pending").select(
        orderby=~db.ai_moderation_queue.created_on, limitby=(0, 50)
    )
    response.title = T("Moderation Queue")
    return dict(rows=rows)


def check():
    """POST: text → moderation result (JSON)."""
    if request.env.request_method != "POST":
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "POST required"})
    text = (request.post_vars.text or "").strip()
    if not text:
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "missing text"})
    if len(text) > 5000:
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "text too long (max 5000 chars)"})

    source_table = request.post_vars.source_table or "manual"
    source_id = request.post_vars.source_id or 0

    result = _moderate(text)
    if "error" in result:
        response.headers["Content-Type"] = "application/json"
        return json.dumps(result)

    # Auto-action
    auto_action = "published"
    if result.get("highest_score", 0) >= 0.7:
        auto_action = "blocked"
    elif result.get("highest_score", 0) >= 0.4:
        auto_action = "flagged"

    # Save in queue
    queue_id = db.ai_moderation_queue.insert(
        source_table=source_table,
        source_id=source_id,
        content_preview=text[:500],
        categories=json.dumps(result.get("categories", {}), ensure_ascii=False),
        scores=json.dumps(result.get("scores", {}), ensure_ascii=False),
        auto_action=auto_action,
        action="pending" if auto_action == "flagged" else auto_action,
        model="llm",
    )
    db.commit()

    response.headers["Content-Type"] = "application/json"
    return json.dumps({
        "queue_id": queue_id,
        "result": result,
        "auto_action": auto_action,
    }, ensure_ascii=False)


def approve():
    """Approve a flagged item (publish)."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user_login"))
    queue_id = request.post_vars.id or request.args(0)
    row = db.ai_moderation_queue(queue_id)
    if row:
        row.update_record(
            action="approved",
            reviewer_id=auth.user.id,
            reviewed_on=request.now,
        )
        db.commit()
    response.headers["Content-Type"] = "application/json"
    return json.dumps({"ok": True})


def reject():
    """Reject a flagged item (block)."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user_login"))
    queue_id = request.post_vars.id or request.args(0)
    row = db.ai_moderation_queue(queue_id)
    if row:
        row.update_record(
            action="rejected",
            reviewer_id=auth.user.id,
            reviewed_on=request.now,
        )
        # Optionally: soft-delete the source content
        if row.source_table and row.source_id:
            table = getattr(db, row.source_table, None)
            if table is not None:
                try:
                    src = table(row.source_id)
                    if src:
                        src.update_record(deleted=True)
                except Exception:
                    pass
        db.commit()
    response.headers["Content-Type"] = "application/json"
    return json.dumps({"ok": True})


def history():
    """Moderation log."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user_login"))
    rows = db(db.ai_moderation_queue.id > 0).select(
        orderby=~db.ai_moderation_queue.created_on, limitby=(0, 100)
    )
    return dict(rows=rows)


# -------------------------------------------------------------------------
# Internal: moderation helper
# -------------------------------------------------------------------------
def _moderate(text):
    """Run moderation on text. Returns dict with categories, scores, highest_score."""
    prompt = f"""วิเคราะห์เนื้อหาต่อไปนี้ในบริบทระบบ Sahana Eden (จัดการเหตุฉุกเฉิน):

เนื้อหา: "{text[:1500]}"

ส่งกลับเป็น JSON:
{{
  "categories": {{
    "hate": true/false,
    "harassment": true/false,
    "self_harm": true/false,
    "sexual": true/false,
    "violence": true/false,
    "spam": true/false,
    "misinformation": true/false,
    "pdpa_violation": true/false
  }},
  "scores": {{
    "hate": 0.0,
    "harassment": 0.0,
    "self_harm": 0.0,
    "sexual": 0.0,
    "violence": 0.0,
    "spam": 0.0,
    "misinformation": 0.0,
    "pdpa_violation": 0.0
  }},
  "highest_score": 0.0,
  "highest_category": "",
  "reason": "คำอธิบายสั้นๆ ภาษาไทย"
}}

กฎ:
- pdpa_violation = true ถ้ามีเลขบัตรประชาชน 13 หลัก, เบอร์โทรศัพท์, หรือข้อมูล sensitive อื่นๆ
- misinformation = true ถ้ามีข้อมูลที่ดูเป็นข่าวลวง/ข้อมูลผิดในบริบทภัีกพิบัติ
- scores เป็น 0.0-1.0
- ส่งกลับเฉพาะ JSON ไม่มี markdown
"""
    try:
        client = AIClient(timeout=60)
        result = client.chat_json(prompt)
    except AIClientError as e:
        return {"error": str(e)}

    # Quick PDPA pattern check (override LLM if needed)
    pdpa_patterns = [
        r"\b\d{1}-\d{4}-\d{5}-\d{2}-\d{1}\b",  # Thai ID format
        r"\b\d{13}\b",  # 13 consecutive digits
        r"\b0[89]\d-\d{3}-\d{4}\b",  # Thai mobile
    ]
    for pat in pdpa_patterns:
        if re.search(pat, text):
            result.setdefault("categories", {})["pdpa_violation"] = True
            result.setdefault("scores", {})["pdpa_violation"] = 1.0
            result["highest_score"] = max(result.get("highest_score", 0), 1.0)
            result["highest_category"] = "pdpa_violation"
            break

    # Ensure highest_score is correct
    scores = result.get("scores", {})
    if scores and not result.get("highest_score"):
        max_cat = max(scores, key=scores.get)
        result["highest_score"] = scores[max_cat]
        result["highest_category"] = max_cat

    return result


# -------------------------------------------------------------------------
# Hook: call from CMS post-create
# -------------------------------------------------------------------------
def _moderate_cms_post(post_id):
    """Hook called after a cms_post is created. Auto-moderates before publish."""
    post = db.cms_post(post_id)
    if not post:
        return
    body = post.body or ""
    if not body.strip():
        return
    # Set the post as "pending review" before moderation
    # (Eden doesn't have a built-in draft state for cms_post; we use the
    # moderation_queue.action as the source of truth.)
    _moderate_and_store(
        source_table="cms_post",
        source_id=post_id,
        text=f"{post.title or ''}\n\n{body}",
    )


def _moderate_and_store(source_table, source_id, text):
    """Run moderation and store result in queue."""
    result = _moderate(text)
    if "error" in result:
        return
    auto_action = "published"
    if result.get("highest_score", 0) >= 0.7:
        auto_action = "blocked"
    elif result.get("highest_score", 0) >= 0.4:
        auto_action = "flagged"
    db.ai_moderation_queue.insert(
        source_table=source_table,
        source_id=source_id,
        content_preview=text[:500],
        categories=json.dumps(result.get("categories", {}), ensure_ascii=False),
        scores=json.dumps(result.get("scores", {}), ensure_ascii=False),
        auto_action=auto_action,
        action="pending" if auto_action == "flagged" else auto_action,
        model="llm",
    )
    db.commit()
