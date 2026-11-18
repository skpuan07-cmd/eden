"""
AI Chatbot controller — Use Case 1: AI Chatbot for citizens and volunteers

Endpoints:
- /eden/ai_chat/                  → Chat UI (HTML page)
- /eden/ai_chat/ask               → POST question, get answer (JSON API)
- /eden/ai_chat/history           → User's conversation history
- /eden/ai_chat/rate/<id>         → Rate an answer (+1 / -1)
- /eden/ai_chat/clear             → Clear current session
- /eden/ai_chat/widget            → Embeddable chat widget (for iframe)

RAG flow:
1. User submits a question (Thai or English)
2. System retrieves relevant chunks from ai_knowledge_chunk table
   (simple keyword + TF-IDF matching; can be upgraded to vector search)
3. Builds a context-augmented prompt
4. Calls z-ai CLI for LLM completion
5. Logs the conversation in ai_chat_log (with consent flag for PDPA)
6. Returns answer + sources to the user
"""
import json
import time
import os

def index():
    """
    Main chat UI.
    """
    # PDPA: show privacy notice; record consent in session
    if request.vars.consent == "yes":
        session.ai_chat_consent = True
    consent_given = session.ai_chat_consent or False

    response.title = T("AI Assistant")
    return dict(
        consent_given=consent_given,
        chat_endpoint=URL("ai_chat", "ask"),
        rate_endpoint=URL("ai_chat", "rate"),
        clear_endpoint=URL("ai_chat", "clear"),
    )


def widget():
    """
    Embeddable chat widget — for use in iframes on other sites.
    """
    response.view = "ai_chat/widget.html"
    return index()


def ask():
    """
    POST endpoint: receive a question, return an answer (JSON).

    Expected POST vars:
        question: str (required)
        session_id: str (optional, defaults to web2py session id)
        language: str (optional, default auto-detect)
    """
    import gluon
    from s3.ai_client import AIClient, AIClientError

    # Only accept POST
    if request.env.request_method != "POST":
        response.view = "generic.json"
        return dict(error="POST required")

    question = (request.post_vars.question or "").strip()
    if not question:
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "missing question"})

    if len(question) > 1000:
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "question too long (max 1000 chars)"})

    # Rate limit: simple per-IP throttle (60/min)
    client_ip = request.env.remote_addr or "unknown"
    one_min_ago = request.now - datetime.timedelta(seconds=60)
    recent_count = db(
        (db.ai_chat_log.ip == client_ip) &
        (db.ai_chat_log.created_on > one_min_ago)
    ).count()
    if recent_count > 60:
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "rate limit exceeded (60/min). Please slow down."})

    # PDPA consent check
    consent_given = bool(session.ai_chat_consent)
    if not consent_given:
        response.headers["Content-Type"] = "application/json"
        return json.dumps({
            "error": "consent_required",
            "message": "กรุณาให้ความยินยอมเก็บข้อมูลการสนทนาก่อน (PDPA consent required)",
            "consent_url": URL("ai_chat", "index", vars={"show_consent": "1"}),
        })

    # RAG: retrieve relevant knowledge chunks
    t0 = time.time()
    chunks = _retrieve_relevant_chunks(question, top_k=5)
    context_text = "\n\n".join(
        f"--- แหล่งข้อมูล #{i+1}: {c.title} ---\n{c.content}"
        for i, c in enumerate(chunks)
    )
    sources = [
        {"title": c.title, "url": c.source_url or "", "type": c.source_type}
        for c in chunks
    ]

    # Build the LLM prompt
    system_prompt = (
        "คุณคือผู้ช่วยของระบบ Sahana Eden สำหรับจัดการเหตุฉุกเฉินและภัยพิบัติ "
        "ตอบคำถามเป็นภาษาไทย (หรือภาษาที่ผู้ใช้ใช้) "
        "อ้างอิงเฉพาะข้อมูลใน context ที่ให้ "
        "หาก context ไม่เพียงพอ บอกว่าไม่ทราบ อย่าคาดเดา "
        "อย่าเปิดเผยข้อมูลส่วนบุคคลของผู้ใดผู้หนึ่ง "
        "ห้ามแนะนำให้ผู้ใช้ติดต่อบุคคลที่ไม่ใช่เจ้าหน้าที่ "
        "ตอบกระชับ ไม่เกิน 200 คำ"
    )
    if context_text:
        full_prompt = f"Context:\n{context_text}\n\nคำถาม: {question}"
    else:
        full_prompt = (
            f"คำถาม: {question}\n\n"
            "หมายเหตุ: ไม่มีข้อมูลในระบบที่เกี่ยวข้องโดยตรง "
            "หากเป็นคำถามทั่วไปเกี่ยวกับภัยพิบัติ ตอบได้แต่ระมัดระวัง"
        )

    # Call the LLM
    try:
        client = AIClient(timeout=60)
        result = client.chat(full_prompt, system=system_prompt)
    except AIClientError as e:
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": f"AI service unavailable: {str(e)}"})

    answer = result.get("content", "")
    usage = result.get("usage", {})
    latency_ms = int((time.time() - t0) * 1000)

    # Log the conversation (PDPA-compliant)
    chat_log_id = db.ai_chat_log.insert(
        session_id=response.session_id[:128] if response.session_id else "no-session",
        user_id=auth.user.id if auth.user else None,
        question=question,
        answer=answer,
        context_used=context_text[:4000] if context_text else None,
        sources=json.dumps(sources, ensure_ascii=False) if sources else None,
        ip=client_ip,
        user_agent=(request.env.http_user_agent or "")[:256],
        model=result.get("model", ""),
        tokens_prompt=usage.get("prompt_tokens", 0),
        tokens_completion=usage.get("completion_tokens", 0),
        latency_ms=latency_ms,
        language="auto",
        created_on=request.now,
        consent_given=consent_given,
    )
    db.commit()

    response.headers["Content-Type"] = "application/json"
    return json.dumps({
        "answer": answer,
        "sources": sources,
        "chat_log_id": chat_log_id,
        "latency_ms": latency_ms,
        "model": result.get("model"),
    }, ensure_ascii=False)


def history():
    """
    Show conversation history for the current user (or session).
    """
    if not auth.user:
        redirect(URL("default", "user/login", vars={"_next": URL("ai_chat", "history")}))

    rows = db(db.ai_chat_log.user_id == auth.user.id).select(
        orderby=~db.ai_chat_log.created_on, limitby=(0, 50)
    )
    return dict(rows=rows)


def rate():
    """
    POST: rate an answer (+1 / -1).
    """
    if request.env.request_method != "POST":
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "POST required"})
    chat_log_id = request.post_vars.id
    rating = request.post_vars.rating
    comment = request.post_vars.comment
    if rating not in ("-1", "0", "1"):
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "invalid rating"})
    row = db.ai_chat_log(chat_log_id)
    if not row:
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "not found"})
    row.update_record(rating=int(rating), feedback_comment=comment)
    db.commit()
    response.headers["Content-Type"] = "application/json"
    return json.dumps({"ok": True})


def clear():
    """Clear the current chat session (clears consent flag)."""
    session.ai_chat_consent = None
    response.headers["Content-Type"] = "application/json"
    return json.dumps({"ok": True})


def consent():
    """Show the privacy notice / consent form."""
    return dict()


def consent_give():
    """POST: record consent in session."""
    session.ai_chat_consent = True
    response.headers["Content-Type"] = "application/json"
    return json.dumps({"ok": True, "redirect": URL("ai_chat", "index")})


def consent_withdraw():
    """POST: withdraw consent (clears session flag)."""
    session.ai_chat_consent = None
    response.headers["Content-Type"] = "application/json"
    return json.dumps({"ok": True, "redirect": URL("ai_chat", "consent")})


# -------------------------------------------------------------------------
# RAG retrieval helper
# -------------------------------------------------------------------------
def _retrieve_relevant_chunks(question, top_k=5):
    """
    Retrieve relevant knowledge chunks for a given question.

    Implementation note: this is a simple keyword + LIKE-based retrieval.
    For better quality, upgrade to vector similarity search using
    pgvector (PostgreSQL) or a dedicated vector store (Qdrant, ChromaDB).
    """
    # Tokenize question (simple whitespace split — works okay for Thai with spaces)
    # For Thai without spaces, consider using PyThaiNLP.word_tokenize
    keywords = [w.strip("?.!,") for w in question.split() if len(w.strip()) > 2]
    if not keywords:
        return []

    # Build OR query on content/title
    query = (db.ai_knowledge_chunk.is_public == True) & \
            (db.ai_knowledge_chunk.deleted == False)
    like_conditions = None
    for kw in keywords[:8]:  # cap to 8 keywords
        cond = (db.ai_knowledge_chunk.content.contains(kw)) | \
               (db.ai_knowledge_chunk.title.contains(kw))
        if like_conditions is None:
            like_conditions = cond
        else:
            like_conditions = like_conditions | cond
    if like_conditions is not None:
        query = query & like_conditions

    return db(query).select(orderby=~db.ai_knowledge_chunk.last_indexed, limitby=(0, top_k))


# Import datetime at end to avoid name shadowing issues in web2py models
import datetime
