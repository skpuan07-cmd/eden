"""
AI Voice controller — Use Case 9: Voice interface (STT + TTS)

Allows users (especially field volunteers) to:
- Upload an audio file → transcribe via ASR (Whisper)
- Speak a command → execute and reply with TTS audio
- Convert any text to speech (TTS) for accessibility

Endpoints:
- /eden/ai_voice/                → voice interface UI
- /eden/ai_voice/transcribe      → POST audio file → transcript (JSON)
- /eden/ai_voice/speak           → POST text → audio file (returns download URL)
- /eden/ai_voice/command         → POST audio → transcript → execute intent → reply audio
- /eden/ai_voice/history         → user's voice logs
"""
import json
import os
import tempfile
from s3.ai_client import AIClient, AIClientError


def index():
    """Voice interface UI."""
    response.title = T("AI Voice Assistant")
    return dict()


def transcribe():
    """POST audio file → transcript."""
    if request.env.request_method != "POST":
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "POST required"})

    upload = request.vars.file
    if not hasattr(upload, "file"):
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "no audio uploaded"})

    # Save to temp file (ASR requires file path)
    ext = os.path.splitext(upload.filename)[1] or ".wav"
    fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="voice_")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(upload.file.read())
        upload.file.close()

        # Save copy in uploads
        try:
            uploaded = db.ai_voice_log.audio_file.store(upload.file, filename=upload.filename)
        except Exception:
            uploaded = None

        log_id = db.ai_voice_log.insert(
            user_id=auth.user.id if auth.user else None,
            audio_file=uploaded,
            language="auto",
            ip=request.env.remote_addr,
        )
        db.commit()

        try:
            client = AIClient(timeout=120)
            result = client.transcribe_audio(tmp_path)
        except AIClientError as e:
            response.headers["Content-Type"] = "application/json"
            return json.dumps({"error": str(e), "log_id": log_id})

        transcript = result["text"]
        db.ai_voice_log(log_id).update_record(transcript=transcript)
        db.commit()

        response.headers["Content-Type"] = "application/json"
        return json.dumps({
            "log_id": log_id,
            "transcript": transcript,
        }, ensure_ascii=False)
    finally:
        try: os.unlink(tmp_path)
        except OSError: pass


def speak():
    """POST text → audio file."""
    if request.env.request_method != "POST":
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "POST required"})
    text = (request.post_vars.text or "").strip()
    if not text:
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "missing text"})
    if len(text) > 500:
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "text too long (max 500 chars)"})

    voice = request.post_vars.voice or "tongtong"
    speed = float(request.post_vars.speed or 1.0)

    # Output path in Eden uploads/voice/
    out_dir = os.path.join(request.folder, "uploads", "ai_voice")
    os.makedirs(out_dir, exist_ok=True)
    import uuid
    filename = f"tts_{uuid.uuid4().hex}.wav"
    out_path = os.path.join(out_dir, filename)

    try:
        client = AIClient(timeout=60)
        client.synthesize_speech(text, output_path=out_path, voice=voice, speed=speed, fmt="wav")
    except AIClientError as e:
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": str(e)})

    # Return a download URL
    download_url = URL("ai_voice", "download", args=filename)
    response.headers["Content-Type"] = "application/json"
    return json.dumps({"audio_url": download_url, "filename": filename, "text": text})


def download():
    """Serve a generated TTS audio file (restricted to ai_voice uploads)."""
    filename = request.args(0)
    if not filename or not filename.startswith("tts_") or not filename.endswith(".wav"):
        raise HTTP(404, "not found")
    path = os.path.join(request.folder, "uploads", "ai_voice", filename)
    if not os.path.exists(path):
        raise HTTP(404, "not found")
    response.headers["Content-Type"] = "audio/wav"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response.stream(path, chunk_size=4096)


def command():
    """POST audio → transcript → execute intent → reply audio (full voice loop)."""
    if request.env.request_method != "POST":
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "POST required"})

    upload = request.vars.file
    if not hasattr(upload, "file"):
        response.headers["Content-Type"] = "application/json"
        return json.dumps({"error": "no audio uploaded"})

    # 1) Save audio → transcribe
    ext = os.path.splitext(upload.filename)[1] or ".wav"
    fd, tmp_audio = tempfile.mkstemp(suffix=ext, prefix="voice_cmd_")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(upload.file.read())
        upload.file.close()

        try:
            client = AIClient(timeout=180)
            asr_result = client.transcribe_audio(tmp_audio)
        except AIClientError as e:
            return json.dumps({"error": f"ASR failed: {e}"})

        transcript = asr_result["text"]
        if not transcript:
            return json.dumps({"error": "empty transcript", "log_id": None})

        # 2) Classify intent
        intent_prompt = f"""ผู้ใช้พูดว่า: "{transcript}"

จำแนก intent เป็นหนึ่งใน:
- query_inventory: ถามเกี่ยวกับสต็อกสินค้า
- query_shelter: ถามเกี่ยวกับศูนย์พักพิง
- query_org: ถามเกี่ยวกับองค์กร/เจ้าหน้าที่
- create_report: ต้องการสร้างรายงาน
- help: ขอความช่วยเหลือ
- other: อื่นๆ

ตอบเฉพาะชื่อ intent บรรทัดเดียว."""
        intent_result = client.chat(intent_prompt)
        intent = intent_result["content"].strip().split("\n")[0].strip().lower()

        # 3) Generate reply
        reply_prompt = f"""ผู้ใช้พูดว่า: "{transcript}"
Intent: {intent}

ปฏิเสธอย่างสุภาพถ้าเป็น "other" หรือ "help" ที่ไม่สามารถทำได้ทันที.
สำหรับ query_* intents, ตอบสั้นๆ ว่าระบบกำลังดึงข้อมูล และจะแสดงผลบนหน้าจอ.
ตอบภาษาไทยกระชับ 1-2 ประโยค.
"""
        reply_text = client.chat(reply_prompt).get("content", "รับทราบครับ")

        # 4) TTS the reply
        out_dir = os.path.join(request.folder, "uploads", "ai_voice")
        os.makedirs(out_dir, exist_ok=True)
        import uuid
        filename = f"tts_{uuid.uuid4().hex}.wav"
        out_path = os.path.join(out_dir, filename)
        client.synthesize_speech(reply_text, output_path=out_path)

        # 5) Log
        log_id = db.ai_voice_log.insert(
            user_id=auth.user.id if auth.user else None,
            transcript=transcript,
            intent=intent,
            response_text=reply_text,
            response_audio_file=filename,
            ip=request.env.remote_addr,
        )
        db.commit()

        return json.dumps({
            "log_id": log_id,
            "transcript": transcript,
            "intent": intent,
            "reply_text": reply_text,
            "reply_audio_url": URL("ai_voice", "download", args=filename),
        }, ensure_ascii=False)
    finally:
        try: os.unlink(tmp_audio)
        except OSError: pass


def history():
    """User's voice command history."""
    if not auth.user:
        redirect(URL("default", "user_login"))
    rows = db(db.ai_voice_log.user_id == auth.user.id).select(
        orderby=~db.ai_voice_log.created_on, limitby=(0, 30)
    )
    return dict(rows=rows)
