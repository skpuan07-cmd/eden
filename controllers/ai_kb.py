"""
AI Knowledge Base controller — Use Case 8: RAG knowledge base admin

Admin UI for managing the ai_knowledge_chunk table:
- ingest_cms_posts   — index all public CMS posts into the knowledge base
- ingest_pages       — index static help pages
- ingest_url         — fetch + index an external URL (e.g. wiki page)
- list_chunks        → browse all indexed chunks
- chunk/<id>         → view/edit a single chunk
- delete/<id>        → delete a chunk
- rebuild_index      → re-embed all chunks (for vector search)
"""
import json
import os
from s3.ai_client import AIClient, AIClientError


def index():
    """Admin dashboard: stats + ingestion actions."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user_login"))
    total = db(db.ai_knowledge_chunk.id > 0).count()
    by_source = {}
    rows = db(db.ai_knowledge_chunk.id > 0).select(
        db.ai_knowledge_chunk.source_type, db.ai_knowledge_chunk.id, distinct=True
    )
    for r in rows:
        by_source[r.source_type] = by_source.get(r.source_type, 0) + 1
    response.title = T("AI Knowledge Base")
    return dict(total=total, by_source=by_source)


def ingest_cms_posts():
    """Index all public CMS posts as knowledge chunks."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user_login"))

    # Eden uses lazy table loading — trigger it via current.s3db
    try:
        from gluon import current
        s3db = current.s3db
        table = s3db.cms_post  # triggers lazy load
    except Exception as e:
        return dict(error=f"could not load cms_post table: {e}")

    posts = db(
        (table.deleted == False) &
        (table.date <= request.now)
    ).select()
    inserted = 0
    for p in posts:
        # Skip if already indexed
        exists = db(
            (db.ai_knowledge_chunk.source_type == "cms_post") &
            (db.ai_knowledge_chunk.source_id == p.id)
        ).select().first()
        if exists:
            continue
        # Split into ~500-char chunks
        body = p.body or ""
        chunks = _split_text(body, max_chars=500)
        for i, c in enumerate(chunks):
            db.ai_knowledge_chunk.insert(
                source_type="cms_post",
                source_id=p.id,
                source_url=URL("cms", "post", args=p.id, scheme=True),
                title=p.title or f"Post #{p.id}",
                content=c,
                chunk_index=i,
                language="en",
                is_public=True,
                last_indexed=request.now,
            )
            inserted += 1
    db.commit()
    return dict(ingested=inserted, total_posts=len(posts))


def ingest_url():
    """POST: fetch an external URL + index its content."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user_login"))
    if request.env.request_method != "POST":
        return dict(error="POST required")
    url = request.post_vars.url
    if not url:
        return dict(error="missing url")

    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SahanaEden-KB/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return dict(error=f"fetch failed: {e}")

    # Strip HTML tags (simple)
    import re
    text = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    chunks = _split_text(text, max_chars=500)
    inserted = 0
    for i, c in enumerate(chunks):
        if len(c) < 50:  # skip tiny chunks
            continue
        db.ai_knowledge_chunk.insert(
            source_type="external_url",
            source_url=url,
            title=url[:128],
            content=c,
            chunk_index=i,
            language="en",
            is_public=True,
            last_indexed=request.now,
        )
        inserted += 1
    db.commit()
    return dict(ingested=inserted, url=url)


def list_chunks():
    """Browse all knowledge chunks."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user_login"))
    rows = db(db.ai_knowledge_chunk.id > 0).select(
        orderby=~db.ai_knowledge_chunk.last_indexed, limitby=(0, 100)
    )
    return dict(rows=rows)


def chunk():
    """View a single chunk."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user_login"))
    chunk_id = request.args(0)
    row = db.ai_knowledge_chunk(chunk_id) or redirect(URL("ai_kb", "list_chunks"))
    return dict(row=row)


def delete():
    """Delete a chunk (soft delete)."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user_login"))
    chunk_id = request.args(0) or request.post_vars.id
    row = db.ai_knowledge_chunk(chunk_id)
    if row:
        row.update_record(deleted=True)
        db.commit()
    response.headers["Content-Type"] = "application/json"
    return json.dumps({"ok": True})


def rebuild_index():
    """Re-embed all chunks (placeholder — vector embedding setup is optional)."""
    if not auth.s3_has_role("ADMIN"):
        redirect(URL("default", "user_login"))
    rows = db(db.ai_knowledge_chunk.deleted == False).select()
    return dict(total=len(rows), note="Embeddings not yet implemented in this version. Add pgvector + text-embedding-3-large to enable.")


def _split_text(text, max_chars=500):
    """Split text into chunks at sentence boundaries if possible."""
    if len(text) <= max_chars:
        return [text]
    chunks = []
    # Simple sentence split by ., !, ?
    import re
    sentences = re.split(r"(?<=[.!?])\s+", text)
    current = ""
    for s in sentences:
        if len(current) + len(s) + 1 <= max_chars:
            current = (current + " " + s).strip()
        else:
            if current:
                chunks.append(current)
            current = s
    if current:
        chunks.append(current)
    return chunks
