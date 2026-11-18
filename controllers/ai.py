"""
AI landing page controller.

Single entry point for all AI modules — accessible from the main Eden menu
as "AI Assistant". Lists all 10 use cases with descriptions and links.
"""
def index():
    """AI features dashboard — the main entry point."""
    from gluon.storage import Storage
    response.title = T("AI Assistant")
    features = [
        Storage(
            name=T("Chatbot"),
            url=URL("ai_chat", "index"),
            icon="💬",
            desc=T("Ask questions about disaster management in Thai or English. RAG-powered with knowledge base."),
            use_case=1,
            auth="public",
        ),
        Storage(
            name=T("OCR — Document Extraction"),
            url=URL("ai_ocr", "index"),
            icon="📷",
            desc=T("Upload images of ID cards, invoices, forms — AI extracts data into structured JSON."),
            use_case=2,
            auth="public",
        ),
        Storage(
            name=T("Predictive Analytics"),
            url=URL("ai_analytics", "index"),
            icon="📊",
            desc=T("30-day forecasts for inventory demand, shelter occupancy, and incident counts."),
            use_case=3,
            auth="public",
        ),
        Storage(
            name=T("Imagery Analysis"),
            url=URL("ai_imagery", "index"),
            icon="🛰",
            desc=T("Analyze satellite/drone/field photos: flood extent, building damage, road passability."),
            use_case=4,
            auth="public",
        ),
        Storage(
            name=T("Translation"),
            url=URL("ai_translate", "index"),
            icon="🌐",
            desc=T("Auto-translate UI strings to other languages using LLM, with human review queue."),
            use_case=5,
            auth="admin",
        ),
        Storage(
            name=T("Natural Language Query"),
            url=URL("ai_query", "index"),
            icon="🔍",
            desc=T("Ask data questions in Thai: 'shelters in Chiang Rai with capacity > 100'."),
            use_case=6,
            auth="admin",
        ),
        Storage(
            name=T("Knowledge Base"),
            url=URL("ai_kb", "index"),
            icon="📚",
            desc=T("Manage RAG knowledge base — ingest CMS posts, external URLs, view indexed chunks."),
            use_case=8,
            auth="admin",
        ),
        Storage(
            name=T("Voice Assistant"),
            url=URL("ai_voice", "index"),
            icon="🎤",
            desc=T("Voice interface — transcribe audio, speak text, run voice commands."),
            use_case=9,
            auth="public",
        ),
        Storage(
            name=T("Content Moderation"),
            url=URL("ai_moderation", "index"),
            icon="🛡",
            desc=T("Auto-moderate user content — hate, harassment, PDPA violations. Review queue for admins."),
            use_case=10,
            auth="admin",
        ),
    ]
    return dict(features=features)
