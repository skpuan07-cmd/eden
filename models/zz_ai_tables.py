"""
AI module tables for Sahana Eden.

Defines database tables used by the AI features:
- ai_chat_log          — chatbot conversation logs
- ai_knowledge_chunk   — RAG knowledge base chunks (with embeddings)
- ai_ocr_job           — OCR extraction jobs (with status)
- ai_translation_job   — batch translation jobs
- ai_moderation_queue  — content moderation review queue
- ai_forecast          — predictive analytics output
- ai_query_log         — Natural Language Query audit log
- ai_voice_log         — voice interface transcripts
- ai_imagery_job       — satellite imagery analysis jobs

Loaded as a web2py model file (alphabetically ordered: ai_tables.py
runs before the standard 00_*.py files).
"""
# Models are executed in the web2py environment, so `db`, `request`, etc.
# are already in scope. We import them defensively so this file can also
# be imported in isolation (e.g. from tests).
try:
    db
    current
    auth
    request
    T
except NameError:
    db = None
    current = None
    auth = None
    request = None
    T = lambda s: s

if db is not None:
    # -----------------------------------------------------------------
    # Common base fields (mimics Eden's s3base_fields without depending on it)
    # -----------------------------------------------------------------
    def _base_fields():
        from gluon import Field
        from datetime import datetime
        return [
            Field("uuid", length=128),
            Field("mci", "integer", default=0),
            Field("deleted", "boolean", default=False),
            Field("created_on", "datetime", default=datetime.utcnow),
            Field("modified_on", "datetime", update=datetime.utcnow),
        ]

    # -----------------------------------------------------------------
    # ai_chat_log - conversation history with the chatbot
    # -----------------------------------------------------------------
    db.define_table(
        "ai_chat_log",
        Field("session_id", length=128),  # browser session
        Field("user_id", "reference auth_user"),  # NULL if anonymous
        Field("question", "text"),
        Field("answer", "text"),
        Field("context_used", "text"),  # JSON: retrieved chunks
        Field("sources", "text"),  # JSON: list of source URLs/IDs
        Field("ip", length=64),
        Field("user_agent", length=256),
        Field("model", length=64),
        Field("tokens_prompt", "integer"),
        Field("tokens_completion", "integer"),
        Field("latency_ms", "integer"),  # response time
        Field("rating", "integer"),  # user feedback: -1, 0, +1
        Field("feedback_comment", "text"),
        Field("language", length=8),  # detected language
        Field("created_on", "datetime"),
        Field("consent_given", "boolean", default=False),  # PDPA
        *_base_fields(),
    )
    db.ai_chat_log.created_on.requires = None
    db.ai_chat_log.question.requires = IS_NOT_EMPTY()

    # -----------------------------------------------------------------
    # ai_knowledge_chunk - RAG knowledge base
    # -----------------------------------------------------------------
    db.define_table(
        "ai_knowledge_chunk",
        Field("source_type", length=32),  # "cms_post", "page", "wiki", "faq"
        Field("source_id", "integer"),  # FK to source table
        Field("source_url", length=512),
        Field("title", length=256),
        Field("content", "text"),  # the chunk text
        Field("chunk_index", "integer"),  # for multi-chunk docs
        Field("language", length=8, default="en"),
        Field("embedding", "text"),  # JSON list of floats (or pgvector)
        Field("embedding_model", length=64),
        Field("tags", "list:string"),
        Field("is_public", "boolean", default=True),
        Field("last_indexed", "datetime"),
        *_base_fields(),
    )
    db.ai_knowledge_chunk.content.requires = IS_NOT_EMPTY()
    db.ai_knowledge_chunk.embedding.readable = False
    db.ai_knowledge_chunk.embedding.writable = False

    # -----------------------------------------------------------------
    # ai_ocr_job - OCR extraction queue
    # -----------------------------------------------------------------
    db.define_table(
        "ai_ocr_job",
        Field("user_id", "reference auth_user"),
        Field("document_type", length=32),  # "id_card", "invoice", "form"
        Field("uploaded_file", "upload"),
        Field("extracted_data", "text"),  # JSON
        Field("target_table", length=64),  # where to insert (e.g. "pr_person")
        Field("target_record_id", "integer"),
        Field("status", length=16, default="pending"),  # pending/done/failed
        Field("error_message", "text"),
        Field("consent_given", "boolean", default=False),  # PDPA
        Field("ip", length=64),
        Field("model", length=64),
        *_base_fields(),
    )
    db.ai_ocr_job.document_type.requires = IS_IN_SET(
        ["id_card", "invoice", "shelter_form", "victim_report", "other"]
    )

    # -----------------------------------------------------------------
    # ai_translation_job - batch translation queue
    # -----------------------------------------------------------------
    db.define_table(
        "ai_translation_job",
        Field("source_lang", length=8, default="en"),
        Field("target_lang", length=8),
        Field("string_key", length=256),
        Field("source_text", "text"),
        Field("translated_text", "text"),
        Field("status", length=16, default="pending"),  # pending/reviewed/approved/rejected
        Field("reviewer_id", "reference auth_user"),
        Field("reviewed_on", "datetime"),
        Field("reviewer_comment", "text"),
        Field("model", length=64),
        *_base_fields(),
    )
    db.ai_translation_job.target_lang.requires = IS_IN_SET(
        ["th", "en", "vi", "km", "lo", "my", "id", "ms", "zh-cn", "ja", "ko"]
    )

    # -----------------------------------------------------------------
    # ai_moderation_queue - content moderation
    # -----------------------------------------------------------------
    db.define_table(
        "ai_moderation_queue",
        Field("source_table", length=64),  # "cms_post", "msg_log", etc.
        Field("source_id", "integer"),
        Field("content_preview", "text"),  # first 500 chars
        Field("categories", "text"),  # JSON: hate, harassment, etc.
        Field("scores", "text"),  # JSON: confidence scores per category
        Field("action", length=16, default="pending"),  # pending/approved/rejected/edited
        Field("reviewer_id", "reference auth_user"),
        Field("reviewed_on", "datetime"),
        Field("auto_action", length=16),  # auto-taken: published/blocked/flagged
        Field("model", length=64),
        *_base_fields(),
    )

    # -----------------------------------------------------------------
    # ai_forecast - predictive analytics output
    # -----------------------------------------------------------------
    db.define_table(
        "ai_forecast",
        Field("target_table", length=64),  # e.g. "inv_inv_track"
        Field("target_id", "integer"),  # e.g. item_id
        Field("metric", length=32),  # "quantity", "demand"
        Field("forecast_date", "date"),
        Field("forecast_value", "double"),
        Field("confidence_lower", "double"),
        Field("confidence_upper", "double"),
        Field("horizon_days", "integer"),  # how many days ahead
        Field("model_version", length=32),
        Field("generated_on", "datetime"),
        *_base_fields(),
    )

    # -----------------------------------------------------------------
    # ai_query_log - NLQ audit
    # -----------------------------------------------------------------
    db.define_table(
        "ai_query_log",
        Field("user_id", "reference auth_user"),
        Field("question", "text"),
        Field("interpreted_query", "text"),  # the generated API URL or SQL
        Field("executed", "boolean", default=False),
        Field("result_count", "integer"),
        Field("answer_text", "text"),
        Field("model", length=64),
        Field("latency_ms", "integer"),
        Field("ip", length=64),
        *_base_fields(),
    )

    # -----------------------------------------------------------------
    # ai_voice_log - voice interface transcripts
    # -----------------------------------------------------------------
    db.define_table(
        "ai_voice_log",
        Field("user_id", "reference auth_user"),
        Field("audio_file", "upload"),
        Field("transcript", "text"),
        Field("intent", length=32),  # "query", "create", "update"
        Field("response_text", "text"),
        Field("response_audio_file", "upload"),
        Field("language", length=8, default="th"),
        Field("ip", length=64),
        *_base_fields(),
    )

    # -----------------------------------------------------------------
    # ai_imagery_job - satellite/drone imagery analysis
    # -----------------------------------------------------------------
    db.define_table(
        "ai_imagery_job",
        Field("user_id", "reference auth_user"),
        Field("image_url", length=512),
        Field("uploaded_file", "upload"),
        Field("imagery_type", length=32),  # "satellite", "drone", "field_photo"
        Field("analysis_type", length=32),  # "flood_extent", "building_damage", "road_passability"
        Field("result_json", "text"),  # full analysis output
        Field("result_summary", "text"),
        Field("location_id", "integer"),  # FK to gis_location (set to integer to avoid lazy-table resolution issues)
        Field("status", length=16, default="pending"),
        Field("model", length=64),
        *_base_fields(),
    )
