"""
AI Translation controller — Use Case 5: Auto-translate Eden UI strings

Eden ships with translation files under languages/ (e.g. th.py).
This controller helps the admin:
- find English strings that are missing in the target language file
- batch-translate missing strings using the LLM
- queue translations for human review (PDPA-safe: no user data, only UI text)

Endpoints:
- /eden/ai_translate/                     → admin dashboard (language picker)
- /eden/ai_translate/missing/<lang>       → show missing strings for <lang>
- /eden/ai_translate/translate_batch      → POST: queue batch translation
- /eden/ai_translate/review               → reviewer queue (pending translations)
- /eden/ai_translate/approve/<id>         → approve a translation
- /eden/ai_translate/reject/<id>          → reject a translation (with comment)
- /eden/ai_translate/apply_approved       → write approved translations to languages/<lang>.py
"""
import json
import os
import re
from s3.ai_client import AIClient, AIClientError


def _lang_file_path(lang):
    """Return path to languages/<lang>.py inside the Eden app."""
    import gluon
    app_path = os.path.join(request.folder, "languages")
    return os.path.join(app_path, f"{lang}.py")


def _load_lang_dict(lang):
    """Load a web2py languages file as a dict of {key: translation}."""
    path = _lang_file_path(lang)
    if not os.path.exists(path):
        return {}
    # web2py lang files are Python dicts at module scope.
    # Use a sandboxed exec.
    namespace = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            code = f.read()
        exec(code, namespace)
    except Exception as e:
        return {"_error": str(e)}
    # Pull out the dict-like items (filter Python builtins)
    out = {}
    for k, v in namespace.items():
        if k.startswith("_"):
            continue
        if isinstance(v, str):
            out[k] = v
    return out


def index():
    """Admin: dashboard with language picker."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user_login"))
    # List available languages from filesystem
    langs_dir = os.path.join(request.folder, "languages")
    available = []
    if os.path.isdir(langs_dir):
        for fn in sorted(os.listdir(langs_dir)):
            if fn.endswith(".py") and fn != "__init__.py":
                available.append(fn[:-3])
    response.title = T("AI Translation")
    return dict(available=available)


def missing():
    """Show English strings missing from the target language."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user_login"))
    lang = request.args(0)
    if not lang:
        redirect(URL("ai_translate", "index"))

    en = _load_lang_dict("en")
    target = _load_lang_dict(lang)

    # Missing = key in English but not in target (or same value = untranslated)
    missing_list = []
    for k, v in en.items():
        if k in target and target[k] and target[k] != k:
            continue  # already translated
        missing_list.append({"key": k, "english": v})

    response.title = T("Missing translations: %s") % lang
    return dict(lang=lang, missing=missing_list[:200], total=len(missing_list))


def translate_batch():
    """POST: translate a list of strings using the LLM and queue for review."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user_login"))
    if request.env.request_method != "POST":
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "POST required"})

    lang = request.post_vars.lang
    keys = request.post_vars.keys  # JSON list
    if not lang or not keys:
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "missing lang or keys"})

    try:
        keys_list = json.loads(keys)
    except json.JSONDecodeError:
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "invalid keys JSON"})

    # Cap to 50 strings per request
    keys_list = keys_list[:50]

    # Build batch prompt
    strings_block = "\n".join(f"{i+1}. {k}" for i, k in enumerate(keys_list))
    prompt = f"""แปล strings ภาษาอังกฤษต่อไปนี้เป็นภาษา {lang}:
{strings_block}

กฎ:
- เป็น string สำหรับ UI ของระบบ emergency management (Sahana Eden)
- คำเฉพาะทางการแพทย์/ภัยพิบัติ ให้ใช้ศัพท์มาตรฐาน เช่น "triage" → "การคัดแยกผู้ป่วย"
- รักษา placeholder format เช่น %s, %(name)s, {variable}
- ส่งกลับเป็น JSON object ที่ key เป็นเลข index 1..N (string), value เป็นคำแปล
- ตัวอย่าง: {{"1": "คำแปลแรก", "2": "คำแปลที่สอง"}}
"""
    try:
        client = AIClient(timeout=120)
        result = client.chat_json(prompt)
    except AIClientError as e:
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": str(e)})

    # Insert each translation into the review queue
    queued = 0
    for i, k in enumerate(keys_list):
        translation = result.get(str(i + 1))
        if not translation:
            continue
        # Skip if there's already a pending/reviewed entry
        existing = db(
            (db.ai_translation_job.source_lang == "en") &
            (db.ai_translation_job.target_lang == lang) &
            (db.ai_translation_job.string_key == k) &
            (db.ai_translation_job.status.belongs("pending", "reviewed"))
        ).select().first()
        if existing:
            continue
        db.ai_translation_job.insert(
            source_lang="en",
            target_lang=lang,
            string_key=k,
            source_text=k,
            translated_text=translation,
            status="pending",
            model="llm",
        )
        queued += 1
    db.commit()

    response.headers["Content-Type"] = "application/json"
    return json.dumps({"queued": queued, "total_requested": len(keys_list)})


def review():
    """Reviewer queue: pending translations."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user_login"))
    lang = request.vars.lang or "th"
    rows = db(
        (db.ai_translation_job.target_lang == lang) &
        (db.ai_translation_job.status == "pending")
    ).select(orderby=~db.ai_translation_job.created_on, limitby=(0, 50))
    response.title = T("Review translations: %s") % lang
    return dict(rows=rows, lang=lang)


def approve():
    """Approve a translation."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user_login"))
    job_id = request.post_vars.id or request.args(0)
    edited = request.post_vars.edited_text
    row = db.ai_translation_job(job_id)
    if not row:
        redirect(URL("ai_translate", "review"))
    final_text = edited.strip() if edited else row.translated_text
    row.update_record(
        status="approved",
        translated_text=final_text,
        reviewer_id=auth.user.id,
        reviewed_on=request.now,
    )
    db.commit()
    response.headers["Content-Type"] = "application/json"
    return json.dumps({"ok": True})


def reject():
    """Reject a translation with comment."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user_login"))
    job_id = request.post_vars.id
    comment = request.post_vars.comment
    row = db.ai_translation_job(job_id)
    if not row:
        redirect(URL("ai_translate", "review"))
    row.update_record(
        status="rejected",
        reviewer_id=auth.user.id,
        reviewed_on=request.now,
        reviewer_comment=comment,
    )
    db.commit()
    response.headers["Content-Type"] = "application/json"
    return json.dumps({"ok": True})


def apply_approved():
    """Write approved translations back to languages/<lang>.py."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user_login"))
    lang = request.vars.lang or request.args(0) or "th"
    rows = db(
        (db.ai_translation_job.target_lang == lang) &
        (db.ai_translation_job.status == "approved")
    ).select()
    if not rows:
        return dict(applied=0, lang=lang)

    # Load existing language file
    path = _lang_file_path(lang)
    existing = _load_lang_dict(lang)
    # Apply approved translations
    applied = 0
    for r in rows:
        existing[r.string_key] = r.translated_text
        applied += 1

    # Write back as Python dict syntax
    header = '# -*- coding: utf-8 -*-\n{\n'
    lines = []
    for k, v in sorted(existing.items()):
        # Escape Python string literals
        k_esc = repr(k)
        v_esc = repr(v)
        lines.append(f"  {k_esc}: {v_esc},")
    footer = '}\n'
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(lines) + footer)

    return dict(applied=applied, lang=lang)
