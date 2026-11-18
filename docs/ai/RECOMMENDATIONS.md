# คำแนะนำการปรับปรุงระบบ Sahana Eden ให้สอดคล้องกับเทคโนโลยีปัจจุบัน

> เอกสารฉบับนี้วิเคราะห์และเสนอแนะทิศทางการปรับปรุงระบบ Sahana Eden (web2py + Python) ใน 3 มิติ: **การนำ AI มาเป็นผู้ช่วย**, **ความมั่นคงปลอดภัยไซเบอร์ (Cyber Security)**, และ**การปฏิบัติตาม พ.ร.บ. คุ้มครองข้อมูลส่วนบุคคล (PDPA)**
>
> คำแนะนำทั้งหมดผูกกับจุดที่ระบบ Eden มีอยู่จริง (โมดูล gis, org, hrm, inv, dvr, cms, msg, etc.) และระบุเทคโนโลยีเฉพาะที่แนะนำให้ใช้

---

## สารบัญ

- [ภาคที่ 1: การนำ AI มาเป็นผู้ช่วยในระบบ Sahana Eden](#ภาคที่-1-การนำ-ai-มาเป็นผู้ช่วยในระบบ-sahana-eden)
- [ภาคที่ 2: การปรับปรุงด้าน Cyber Security](#ภาคที่-2-การปรับปรุงด้าน-cyber-security)
- [ภาคที่ 3: การปฏิบัติตาม PDPA (พ.ร.บ. คุ้มครองข้อมูลส่วนบุคคล 2562)](#ภาคที่-3-การปฏิบัติตาม-pdpa-พรบ-คุ้มครองข้อมูลส่วนบุคคล-2562)
- [ภาคที่ 4: Roadmap การปรับปรุงแบ่งตามระยะ](#ภาคที่-4-roadmap-การปรับปรุงแบ่งตามระยะ)
- [ภาคที่ 5: สรุปและลำดับความสำคัญ](#ภาคที่-5-สรุปและลำดับความสำคัญ)

---

## ภาคที่ 1: การนำ AI มาเป็นผู้ช่วยในระบบ Sahana Eden

Sahana Eden เป็นระบบบริหารจัดการเหตุฉุกเฉินที่มีข้อมูลจำนวนมาก (people, organizations, inventory, locations, incidents, messages) — ทำให้เหมาะกับการนำ AI มาช่วยในงาน 3 ประเภทคือ **1) รับมือกับผู้ใช้ปลายทาง** (ประชาชน/อาสาสมัคร), **2) ประมวลผลข้อมูลภายใน** (extract, classify, search), และ **3) สนับสนุนการตัดสินใจ** (predict, recommend)

### 1.1 AI Chatbot สำหรับประชาชนและอาสาสมัคร

**ปัญหาที่แก้:** ในช่วงภัยพิบัติ ประชาชนและอาสาสมัครต้องการข้อมูลด่วน (ตำแหน่งศูนย์พักพิง, เส้นทางอพยพ, เบอร์ติดต่อ, ความต้องการอาสาสมัคร) แต่ call center มีจำกัด

**แนวทาง:** สร้าง AI chatbot บน web2py controller ใหม่ (เช่น `controllers/ai_chat.py`) เชื่อมกับ LLM API ผ่าน REST + RAG เพื่อดึงข้อมูลจาก Eden

**เทคโนโลยีที่แนะนำ:**
- **LLM:** Claude 3.5 Sonnet หรือ GPT-4o (ผ่าน Z.ai API หรือ OpenAI)
- **Embedding:** text-embedding-3-large (OpenAI) หรือ BGE-M3 (开源 รองรับภาษาไทย)
- **Vector Store:** pgvector (บน PostgreSQL) หรือ Qdrant
- **Framework:** LangChain หรือ LlamaIndex (Python)

**ขั้นตอนการทำ:**
1. สร้าง vector embeddings จากข้อมูลสาธารณะใน Eden (ศูนย์พักพิง, องค์กร, ประกาศ CMS) — ห้าม embedding ข้อมูล sensitive เช่น ข้อมูลผู้ประสบภัย
2. สร้าง chatbot endpoint ที่รับคำถามภาษาไทย → retrieve จาก vector store → ส่ง context + คำถามไปยัง LLM → ตอบ
3. เชื่อมเข้า Line OA / Facebook Messenger / Telegram (ผ่าน webhook ของ Eden module `msg`)
4. เก็บ chat log ในตาราง `ai_chat_log` ใหม่ใน Eden

**ตัวอย่าง integration code ใน web2py:**
```python
# controllers/ai_chat.py
def index():
    """AI chatbot endpoint สำหรับประชาชน"""
    question = request.post_vars.question
    if not question:
        return dict(error="missing question")

    # RAG: retrieve relevant context from Eden public data
    context = retrieve_from_vector_store(question, top_k=5)

    # สร้าง prompt และเรียก LLM
    prompt = build_prompt(question, context, system="คุณคือผู้ช่วยของระบบ Sahana Eden ตอบคำถามเกี่ยวกับภัยพิบัติเป็นภาษาไทย อ้างอิงเฉพาะข้อมูลใน context")
    answer = call_llm_api(prompt)

    # log สนทนา
    db.ai_chat_log.insert(
        question=question,
        answer=answer,
        context_used=context,
        ip=request.env.remote_addr,
        created_on=request.now,
    )
    return dict(answer=answer)
```

**ข้อควรระวัง:**
- ห้ามให้ chatbot ตอบคำถามที่เข้าถึงข้อมูลส่วนบุคคล (PDPA risk) เช่น "ข้อมูลผู้ประสบภัยชื่อ X"
- กำหนด system prompt แบบเข้มงวด ห้าม hallucinate นอก context
- ใช้ content moderation (OpenAI Moderation API) กรองคำถามที่ไม่เหมาะสม

### 1.2 AI สำหรับ OCR และ Data Extraction

**ปัญหาที่แก้:** ในสนามจริง อาสาสมัครถ่ายเอกสาร/บัตรประชาชน/ใบเบิก แล้วกรอกข้อมูลเข้า Eden ด้วยมือ — ช้าและผิดพลาด

**แนวทาง:** ใช้ AI OCR และ LLM ดึงข้อมูลจากรูป → populate form ใน Eden อัตโนมัติ

**Use cases เฉพาะใน Eden:**
- **บัตรประชาชนไทย** → ดึง ชื่อ, นามสกุล, เลขบัตร, ที่อยู่ → ใส่ใน `pr_person` + `auth_user` (สำหรับ register)
- **ใบเบิกวัสดุ** → ดึก ชื่อสินค้า, จำนวน, หน่วย → ใส่ใน `inv_inv_item` + `req_req`
- **ทะเบียนรถกู้ภาย** → ดึก เลขทะเบียน, ยี่ห้อ → ใส่ใน `vehicle_vehicle`
- **แบบฟอร์มรายงานผู้ประสบภัย** → ดึงข้อมูลผู้ประสบภัย → ใส่ใน `dvr_case` (PDPA: ข้อมูล sensitive ต้องเข้ารหัสที่ rest)

**เทคโนโลยีที่แนะนำ:**
- **OCR:** Google Document AI (แม่นยำสำหรับเอกสารไทย), Tesseract 5 + Thai language pack (self-host, ฟรี), AWS Textract
- **LLM for extraction:** Claude 3.5 Sonnet (vision capability) — ส่งรูปเข้าไปตรงๆ แล้วให้ LLM สร้าง JSON structured output
- **Thai NER:** PyThaiNLP + WangChanBERTa สำหรับ named entity recognition เฉพาะภาษาไทย

**ตัวอย่าง flow:**
```python
# controllers/ocr.py
def extract_id_card():
    """อัปโหลดรูปบัตรประชาชน → ดึงข้อมูล → แสดง form พร้อมกรอก"""
    upload = request.vars.file
    if not upload:
        return dict(error="no file")

    # เรียก LLM ที่รองรับ vision
    result = call_vision_llm(upload.file, prompt="""
        ดึงข้อมูลจากบัตรประชาชนไทยนี้ ส่งกลับเป็น JSON ที่มี field:
        - first_name_th, last_name_th
        - first_name_en, last_name_en
        - id_number (13 หลัก)
        - address (ที่อยู่ตามบัตร)
        - birth_date (YYYY-MM-DD)
        อย่าคาดเดาข้อมูลที่ไม่เห็นในรูป
    """)
    # ส่ง JSON กลับให้ frontend กรอก form
    return dict(data=result)
```

**PDPA caveat:** รูปบัตรประชาชนคือ "ข้อมูลส่วนบุคคล" และเลขบัตร 13 หลักถือเป็น "ข้อมูลอ่อนไหว" — ต้อง:
1. เข้ารหัสที่ at-rest (DB column-level encryption)
2. ไม่เก็บรูปใน S3/public bucket ถ้าไม่จำเป็น — ลบหลัง extract แล้ว
3. บันทึก consent ใน `consent_log` ว่าเจ้าของบัตรยินยอม

### 1.3 AI สำหรับ Predictive Analytics

**ปัญหาที่แก้:** ระบบ Eden เก็บข้อมูลย้อนหลังได้มาก (การเกิดเหตุ, ความต้องการสินค้า, การอพยพ) แต่ใช้แค่ reporting ไม่ได้ใช้ predict

**แนวทาง:** สร้าง ML models ที่เรียนรู้จากข้อมูลใน Eden เพื่อ:
- **พยากรณ์ความต้องการสินค้า:** ในมอsoon season ภาคใต้ต้องการเต็นท์กี่หลัง? น้ำดื่มกี่ลัง? → เตรียมล่วงหน้า
- **พยากรณ์จำนวนผู้อพยพ:** จากข้อมูลน้ำท่วมย้อนหลัง + พยากรณ์ฝน → จำนวนคนที่ต้องเข้าศูนย์พักพิง
- **พยากรณ์ความเสี่ยงเหตุ:** hot-spot ในกรุงเทพฯ ที่มักเกิดเพลิงไหม้ในช่วงไหนของปี
- **Classification ความรุนแรงเหตุ:** ใช้ NLP กับรายงานเหตุฉุกเฉินใน `cms_post` → จัดระดับ severity อัตโนมัติ

**เทคโนโลยี:**
- **Time series forecasting:** Prophet (Facebook) หรือ NeuralProphet — ง่าย ทำนายได้ดี
- **Gradient boosting:** XGBoost / LightGBM สำหรับ tabular prediction
- **Deep learning:** LSTM/Transformer สำหรับ sequence ที่ซับซ้อน
- **MLOps:** MLflow สำหรบ track experiments, DVC สำหรับ versioning dataset

**จุดเชื่อม Eden:**
```python
# สร้าง nightly scheduled task ใน Eden scheduler
# scheduler_task: 'forecast_inventory_demand'
def forecast_inventory_demand():
    """รันทุกคืน พยากรณ์ความต้องการสินค้า 30 วันข้างหน้า"""
    import pandas as pd
    from prophet import Prophet

    # ดึงข้อมูล inv_inv_item movement 12 เดือนย้อนหลัง
    df = pd.DataFrame(db(
        (db.inv_inv_track.deleted == False) &
        (db.inv_inv_track.date > request.now - datetime.timedelta(days=365))
    ).select(db.inv_inv_track.item_id, db.inv_inv_track.quantity, db.inv_inv_track.date).as_list())

    # รัน Prophet
    m = Prophet(yearly_seasonality=True, weekly_seasonality=True)
    for item_id in df.item_id.unique():
        item_df = df[df.item_id == item_id].rename(columns={'date': 'ds', 'quantity': 'y'})
        m.fit(item_df)
        future = m.make_future_dataframe(periods=30)
        forecast = m.predict(future)
        # เขียนผลลัพธ์กลับเป็นตาราง inv_forecast
        save_forecast(item_id, forecast.tail(30))
```

### 1.4 AI สำหรับ Image Recognition (ดาวเทียม + ภาพถ่ายภาคพื้น)

**ปัญหาที่แก้:** หลังเหตุการณ์น้ำท่วม/แผ่นดินไหว ต้องประเมินความเสียหายเร็วที่สุด แต่ต้องใช้คนดูภาพดาวเทียมทีละภาพ

**แนวทาง:**
- **Satellite imagery analysis:** ใช้ computer vision ตรวจจับ:
  - ขอบเขตน้ำท่วม (semantic segmentation)
  - อาคารที่พังเสียหาย (building damage classification — pre/post event)
  - ถนนที่เข้าไม่ได้ (road passability)
- **Drone imagery:** สำหรับพื้นที่เฉพาะเจาะจง
- **Field photos:** อาสาสมัครถ่ายรูปส่งเข้า Eden → AI classify ประเภทเหตุการณ์อัตโนมัติ

**เทคโนโลยีที่แนะนำ:**
- **Pre-trained models:** Meta's SAM (Segment Anything Model) สำหรับ segmentation
- **PyTorch + torchvision** สำหรับ custom training
- **Hugging Face** สำหรับ pre-trained models ที่ใช้ภาพถ่ายภาคพื้น
- **Google Earth Engine** สำหรับเข้าถึง satellite imagery + preprocessing
- **xView2** dataset + model (open source สำหรับ building damage assessment)

**จุดเชื่อม Eden:** สร้าง controller `controllers/gis_ai.py` ที่รับภาพ + location → run inference → update `gis_layer_feature` ด้วย damage polygons

### 1.5 AI สำหรับ Translation

**ปัญหาที่แก้:** Sahana Eden รองรับ 18 ภาษา แต่ translation files (`languages/*.py`) ต้องดูแลด้วยมือ → ไม่อัปเดต ภาษาไทยล้าหลัง

**แนวทาง:**
- ใช้ LLM แปล strings จาก English เป็น target language แบบ batch + มีบริบท
- เปรียบเทียบกับ Google Translate API (เร็วกว่า แต่คุณภาพต่ำกว่าสำหรับ technical terms)
- สร้าง workflow: `cron` → detect new strings in source → translate → review → save to `languages/th.py`

**ตัวอย่าง:**
```python
# scripts/translate_strings.py
import requests
from gluon import current
T = current.T

def translate_new_strings(target_lang="th"):
    """ค้นหา strings ใหม่ที่ยังไม่มีใน languages/th.py แล้วแปล"""
    en_strings = load_language_file("en")
    target_strings = load_language_file(target_lang)
    missing = {k: v for k, v in en_strings.items() if k not in target_strings}

    if not missing:
        return "no new strings"

    # เรียก LLM แปลแบบ batch (ส่งหลาย strings พร้อม context)
    prompt = f"แปล strings เหล่านี้เป็นภาษา{target_lang} สำหรับ UI ของระบบ emergency management:\n"
    prompt += "\n".join(f"- {k}" for k in missing.keys())

    translations = call_llm_api(prompt, format="json")
    # บันทึกกลับ
    save_language_file(target_lang, {**target_strings, **translations})
```

**คำแนะนำเพิ่มเติม:**
- ใช้ Neural Machine Translation เฉพาะภาษาใน disaster response (มีศัพท์เฉพาะ เช่น triage, evacuation, casualty)
- ตั้ง review queue: AI แปล → human reviewer (Thai speaker) ตรวจ → commit
- ใช้ terminology base สำหรับคำเฉพาะ (UN OCHA glossary, Thailand DDPM glossary)

### 1.6 AI สำหรับ Natural Language Query

**ปัญหาที่แก้:** ผู้บริหารต้องการข้อมูลแบบ "แสดงศูนย์พักพิงทั้งหมดในจ.เชียงรายที่รองรับได้มากกว่า 100 คน" แต่ต้องใช้ filter UI ที่ซับซ้อน

**แนวทาง:** แปลง natural language → Eden REST API query

**ตัวอย่าง flow:**
1. User พิมพ์ใน chatbox: "shelter ที่เชียงราย capacity > 100"
2. LLM แปลงเป็น S3 URL: `/eden/cr/shelter.json?location.name__like=เชียงราย&capacity__gt=100`
3. ระบบเรียก URL → return JSON → LLM format เป็นภาษาไทย → ตอบ user

**เทคโนโลยี:**
- **Function calling:** ใช้ Claude / GPT-4 function calling ที่กำหนด schema ของ Eden REST API
- **Text-to-SQL (เฉพาะ admin):** สำหรับการ query ที่ซับซ้อน ใช้ LLM สร้าง SQL → execute บน read-only replica

**ข้อควรระวัง:**
- SQL injection: ใช้ parameterized queries เท่านั้น, ห้าม execute LLM output โดยตรง
- PDPA: ห้าม query ข้อมูล sensitive ผ่าน NLQ โดยไม่ผ่าน permission check
- Performance: rate limit + caching

### 1.7 AI สำหรับ Code Assistance และ DevOps (สำหรับทีมพัฒนา)

**ไม่ใช่ฟีเจอร์ใน Eden เอง แต่ช่วยทีมพัฒนา:**

- **GitHub Copilot / Cursor:** สำหรับเขียน Python controllers, YATL views, PyDAL schema
- **Claude Code / GPT-4:** สำหรับ review code, แต่ง test cases
- **AI-powered commit messages:** สร้าง changelog อัตโนมัติ
- **Aider / OpenDevin:** AI pair-programming สำหรับ refactor
- **AI log analyzer:** ตรวจ `errors/` tickets → แนะนำวิธีแก้
- **AI-powered migrations:** ช่วย migrate schema ระหว่าง Eden versions

### 1.8 RAG (Retrieval Augmented Generation) สำหรับ Sahana Knowledge Base

**ปัญหาที่แก้:** อาสาสมัครใหม่ไม่รู้จะดูคู่มือ Eden ที่ไหน (docs กระจัดกระจาย — ReadTheDocs, wiki, mailing list)

**แนวทาง:** สร้าง knowledge base chatbot สำหรับทีม Eden เอง
1. Crawl: eden readthedocs + wiki + GitHub issues + mailing list
2. Embed → pgvector
3. Slack/Discord bot ที่ทีมถามได้ตลอดเวลา "ทำไม migrate แล้วตาราง X หาย?"

**เทคโนโลยี:**
- **LangChain + ChromaDB** หรือ **LlamaIndex + pgvector**
- **Source:** https://eden-asp.readthedocs.io, https://eden.sahanafoundation.org/wiki, GitHub issues

### 1.9 AI สำหรับ Voice Interface

**ปัญหาที่แก้:** ในสนามจริง (ฝนตก, มือเปียก, ใส่ถุงมือ) อาสาสมัครไม่สะดวกพิมพ์ → ต้องการสั่งด้วยเสียง

**แนวทาง:**
- **Speech-to-Text (STT):** Whisper (OpenAI open source) — รองรับภาษาไทยดี, self-host ได้
- **Text-to-Speech (TTS):** Google TTS / Azure TTS / OpenAI TTS — ภาษาไทยเสียงธรรมชาติ
- **Mobile PWA:** ใช้ Web Speech API (browser-native) สำหรับอาสาสมัครที่ใช้มือถือ

**Use case:**
- "เพิ่มคนชื่อ นายสมชาย ในศูนย์พักพิง A" → AI extract → populate form
- "สินค้าคงคลัง น้ำดื่ม เหลือกี่ลัง?" → AI query → พูดตอบ

### 1.10 AI สำหรับ Content Moderation

**ปัญหาที่แก้:** CMS posts และ user-submitted reports อาจมี:
- ข้อมูลเท็จ / ข่าวลวงในภัีกพิบัติ (เช่น "น้ำท่วมถึงกรุงเทพฯ คืนนี้")
- ข้อความสแปม / โฆษณา
- เนื้อหาที่ผิด PDPA (เผยแพร่ข้อมูลผู้ประสบภัยโดยไม่ได้รับ consent)

**แนวทาง:**
- ใช้ **OpenAI Moderation API** ตรวจทุกโพสต์ใน `cms_post` ก่อน publish (hate, harassment, self-harm, violence)
- ใช้ LLM ตรวจ fact-check โพสต์ที่อ้างข้อมูลสำคัญ → compare กับ trusted sources (DDPM, Thai Meteorological Department)
- ใช้ Thai NER ดึงชื่อบุคคล + ID numbers → flag หากเป็นข้อมูล sensitive ที่จะเผยแพร่

---

## ภาคที่ 2: การปรับปรุงด้าน Cyber Security

Sahana Eden ใน default install มีช่องโหว่ด้าน security หลายจุดที่ควรเสริมก่อน deploy จริง

### 2.1 Authentication & Authorization

#### 2.1.1 Multi-Factor Authentication (MFA / 2FA)
web2py มี `auth.settings.multi_login` แต่ต้องเพิ่ม TOTP integration:

```python
# ใน models/00_settings.py
# เปิดใช้ 2FA สำหรับ admin role (บังคับ) + optional สำหรับ user ทั่วไป
auth.settings.two_factor_authentication = True
auth.settings.two_factor_force = (auth.user_group() == "ADMIN")
# ใช้ pyotp library สำหรับ TOTP
# QR code สำหรับ Google Authenticator / Authy
```

**แนะนำให้บังคับ 2FA สำหรับ:** ADMIN, ORG_ADMIN, MAP_ADMIN, DPO (Data Protection Officer)

#### 2.1.2 Password Policy ที่แข็งแรงขึ้น
```python
# ใน models/000_config.py
settings.auth.password_min_length = 12
# เพิ่ม complexity check (ตัวใหญ่/ตัวเล็ก/ตัวเลข/symbol)
auth.settings.password_complexity = {
    "upper": 1, "lower": 1, "digit": 1, "special": 1
}
# ป้องกัน password reuse (เก็บ history 12 รหัสล่าสุด)
auth.settings.password_history = 12
# Lock account หลัง 5 ครั้งผิด → unlock โดย admin เท่านั้น
settings.auth.max_login_attempts = 5
settings.auth.failed_login_lock_timeout = 1800  # 30 นาที
```

#### 2.1.3 Session Management
- Session timeout: 30 นาที idle (default 8 ชม. มากเกินไป)
- Concurrent session limit: 1 session / user
- Session rotation หลัง login สำเร็จ (ป้องกัน session fixation)
- HTTPS-only cookies + SameSite=Strict (default ปัจจุบันคือ Lax — ควรปรับ)

```python
# ใน models/00_settings.py
session.timeout = 1800  # 30 นาที
session.secure() if request.is_https else None
# ปรับ SameSite ใน gluon/main.py: cookie_args['samesite'] = 'Strict'
```

#### 2.1.4 SSO (Single Sign-On) สำหรับองค์กรใหญ่
- OIDC (OpenID Connect) ผ่าน Keycloak หรือ Azure AD
- ลด password fatigue สำหรับ staff ที่ต้องเข้าหลายระบบ
- Centralized audit (login/logout log ที่เดียว)

### 2.2 Encryption

#### 2.2.1 In-Transit (TLS)
- บังคับ TLS 1.3 ที่ Caddy (disable TLS 1.0/1.1/1.2)
- HSTS header: `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
- Certificate: Let's Encrypt หรือใช้ internal CA สำหรับ air-gapped deployment

#### 2.2.2 At-Rest (Column-level Encryption)
ข้อมูล sensitive ใน Eden ที่ควรเข้ารหัส:
- `auth_user.email` — encrypt (เพราะใช้ใน login และเป็น PII)
- `auth_user.password` — already hashed with `pbkdf2_sha512` (OK)
- `pr_person.*` — ข้อมูลบุคคล ควร column-level encrypt
- `dvr_case.*` — ข้อมูลผู้ประสบภัย (sensitive)
- `msg_log.message` — SMS/email content ที่อาจมี PII
- `auth_user.phone` (ถ้าเก็บ)

```python
# ใช้ PyDAL's EncryptedField (Field(type='encrypted', password=KEY))
# หรือ custom type ที่ใช้ cryptography.fernet
from cryptography.fernet import Fernet
import os

# อ่าน key จาก env var (ไม่ใช่ hardcoded!)
FERNET_KEY = os.environ.get("EDEN_ENCRYPTION_KEY")  # 32 bytes base64
cipher = Fernet(FERNET_KEY)

db.auth_user.email.requires = IS_NOT_EMPTY()
db.auth_user.email.widget = SQLFORM.widgets.string.widget
# Override storage type
class EncryptedEmail(StringType):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
    def store(self, value):
        return cipher.encrypt(value.encode()).decode()
    def retrieve(self, value):
        return cipher.decrypt(value.encode()).decode()
# (web2py Field(type=...) custom)
```

**Key management:** ใช้ HashiCorp Vault หรือ AWS KMS — ห้ามเก็บ key ใน source code

#### 2.2.3 Database TDE (Transparent Data Encryption)
สำหรับ PostgreSQL: ใช้ `pgcrypto` extension หรือ encrypt entire volume ที่ OS level (LUKS บน Linux)

### 2.3 OWASP Top 10 (2021) — Protection Map

| OWASP Risk | Eden status | การปรับปรุง |
|-----------|-------------|------------|
| **A01 Broken Access Control** | มี `s3_permission` ACL แต่ default เปิดหมด | Review ACL ทุก controller + ปิด public access ที่ไม่จำเป็น |
| **A02 Cryptographic Failures** | password hashed OK, แต่ sensitive columns ไม่ encrypted | เพิ่ม column encryption (ส่วน 2.2.2) |
| **A03 Injection** | PyDAL ใช้ parameterized queries — ปลอดภัย | ตรวจ custom SQL queries ที่ developer เขียนเอง |
| **A04 Insecure Design** | template default เปิด debug=True | ปิด debug ใน production, security by design review |
| **A05 Security Misconfiguration** | routes.py มี default welcome app | ลบ welcome app, ตั้ง `default_application='eden'` |
| **A06 Vulnerable Components** | web2py 3.3.3 + submodules | รัน `safety check` + `pip-audit` monthly, อัปเดต dependencies |
| **A07 Auth Failures** | ใช้ web2py default | เพิ่ม 2FA, password policy (ส่วน 2.1) |
| **A08 Software/Data Integrity** | ไม่มี SBOM | สร้าง SBOM (CycloneDX), sign releases |
| **A09 Logging/Monitoring** | log แค่ error tickets | เพิ่ม audit log + SIEM (ส่วน 2.5) |
| **A10 SSRF** | ไม่มี outbound HTTP calls ที่ user-controlled | audit `requests.get()` calls ใน code |

### 2.4 HTTP Security Headers

เพิ่ม headers ที่ Caddy หรือใน web2py response:
```
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' cdnjs.cloudflare.com; img-src 'self' data: *.openstreetmap.org *.tile.openstreetmap.org bing.com maps.googleapis.com; connect-src 'self';
X-Content-Type-Options: nosniff
X-Frame-Options: DENY  (หรือ CSP frame-ancestors)
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(self), camera=(), microphone=()
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
Cross-Origin-Opener-Policy: same-origin
```

**Caddy config (เพิ่มใน Caddyfile):**
```
header {
    Content-Security-Policy "default-src 'self'..."
    X-Content-Type-Options "nosniff"
    X-Frame-Options "DENY"
    Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
    Referrer-Policy "strict-origin-when-cross-origin"
}
```

### 2.5 Audit Logging & SIEM

web2py มี `auth_event` table ที่ log login/logout แต่ไม่ครบ — เพิ่ม:

```python
# ใน modules/s3audit.py (สร้างใหม่)
class S3Audit:
    """Audit log สำหรับทุก action ที่สำคัญ (create/update/delete)"""

    AUDITED_TABLES = [
        "auth_user", "auth_group", "auth_membership",
        "pr_person", "dvr_case", "dvr_case_event",
        "inv_inv_item", "req_req", "cr_shelter",
        "cms_post", "msg_log", "sync_repository",
    ]

    def log(self, table, record_id, action, before=None, after=None):
        db.s3_audit_log.insert(
            user_id=auth.user.id if auth.user else None,
            table_name=table,
            record_id=record_id,
            action=action,  # CREATE / UPDATE / DELETE / READ
            before_data=json.dumps(before) if before else None,
            after_data=json.dumps(after) if after else None,
            ip=request.env.remote_addr,
            user_agent=request.env.http_user_agent,
            timestamp=request.now,
        )
```

**ส่ง audit log ไป SIEM:**
- **Wazuh** (open source) หรือ **ELK Stack** — ส่ง log ผ่าน syslog/Filebeat
- สำหรับ enterprise: **Splunk** หรือ **Microsoft Sentinel**
- Alert rules:
  - การ export ข้อมูล > 1000 records / hour (data exfiltration)
  - Login จาก IP ต่างประเทศ (GeoIP)
  - Bulk delete operations
  - Failed login > 5 ครั้ง / นาที

### 2.6 Vulnerability Management

- **Scanner รายเดือน:** `nikto` (web), `nuclei` (templates), `zap-cli` (OWASP ZAP)
- **Dependency scan:** `pip-audit` ทุกครั้งที่ update requirements.txt
- **Container scan:** Trivy หรือ Grype (ถ้า deploy ด้วย Docker)
- **Code scan:** Semgrep (SAST), Bandit (Python)
- **Penetration test:** ปีละ 1 ครั้ง โดยบริษัทภายนอก (สำหรับ mission-critical deployment)

### 2.7 API Security (Eden REST API)

Eden มี REST API ทุก module (`/eden/<controller>/<function>.json`) ที่ต้องป้องกัน:

```python
# ใน models/00_settings.py
# Rate limiting
auth.settings.api_rate_limit = {
    "per_minute": 60,
    "per_hour": 1000,
}
# Token auth (JWT หรือ web2py auth_token)
auth.settings.api_tokens = True  # ออก token ผ่าน /eden/default/user/api_token
# IP allowlist สำหรับ admin endpoints
auth.settings.ip_allowlist = {
    "appadmin": ["10.0.0.0/8", "172.16.0.0/12"],
}
```

- ใช้ **API Gateway** (Kong, Tyk, AWS API Gateway) หน้า Eden สำหรับ rate limit, auth, logging
- ปิด `.xml`/`.csv`/`.pdf` export endpoints สำหรับ user ที่ไม่มีสิทธิ์ (PDPA risk)

### 2.8 Backup & Disaster Recovery

- **Database:** nightly backup → เก็บ 30 วัน (hot), monthly → เก็บ 12 เดือน (cold)
- **Files (uploads/):** sync ไป S3-compatible storage (MinIO, AWS S3, Backblaze B2)
- **Test restore:** ทุก 3 เดือน เพื่อยืนยันว่า backup ใช้ได้จริง
- **RTO/RPO:**
  - RTO (Recovery Time Objective) = 4 ชั่วโมง
  - RPO (Recovery Point Objective) = 24 ชั่วโมง (คืนละ 1 backup)
- **Multi-region:** สำหรับ deployment ระดับชาติ ควรมี hot standby ในภูมิภาคที่ 2

### 2.9 Secrets Management

**ปัจจุบัน (ในแพ็คเกจ):** `mail.login = "...:GMAIL_APP_PASSWORD_PLACEHOLDER"` และ `hmac_key = "akeytochange"` — hardcoded

**ควรเปลี่ยนเป็น:**
```python
# ใน models/000_config.py
import os
settings.mail.login = f"sungkom.pm@gmail.com:{os.environ['GMAIL_APP_PASSWORD']}"
settings.auth.hmac_key = os.environ["EDEN_HMAC_KEY"]  # 64 bytes random
# โหลดจาก /etc/eden/env หรือ HashiCorp Vault
```

**Vault integration:**
```bash
# systemd unit สำหรับ web2py
EnvironmentFile=/etc/eden/env  # ไฟล์ root-only readable
# หรือ
ExecStartPre=/usr/local/bin/vault-env eden  # โหลด secrets จาก Vault → env
```

### 2.10 Container & Infrastructure Security (ถ้าใช้ Docker)

```dockerfile
# Dockerfile hardening
FROM python:3.12-slim AS base
# ไม่ใช้ root
RUN useradd -m -u 1000 eden
USER eden
WORKDIR /home/eden
# Read-only filesystem
# รัน: docker run --read-only --tmpfs /tmp ...
# Cap drop
# docker run --cap-drop ALL --cap-add CHOWN --cap-add SETGID ...
# No-new-privileges
# docker run --security-opt no-new-privileges
```

- ใช้ **distroless** base image (ไม่มี shell → ยากโจมตี)
- **Image scan:** Trivy ก่อน push
- **Network policies:** ถ้าใช้ Kubernetes, จำกัด egress เฉพาะที่จำเป็น

---

## ภาคที่ 3: การปฏิบัติตาม PDPA (พ.ร.บ. คุ้มครองข้อมูลส่วนบุคคล 2562)

PDPA บังคับใช้เต็มรูปแบบตั้งแต่ 1 มิถุนายน 2022 — Sahana Eden ที่เก็บข้อมูลผู้ประสบภัย อาสาสมัคร เจ้าหน้าที่ ต้องปฏิบัติตาม

### 3.1 ภาพรวม PDPA

**หลักการ 7 ข้อ (Section 25):**
1. **Lawfulness** — เก็บข้อมูลต้องมีฐานความชอบด้วยกฎหมาย
2. **Purpose Limitation** — เก็บเพื่อวัตถุประสงค์ที่กำหนดชัด
3. **Data Minimization** — เก็บน้อยที่สุดเท่าที่จำเป็น
4. **Accuracy** — ข้อมูลต้องถูกต้องและอัปเดต
5. **Storage Limitation** — เก็บเฉพาะเท่าที่จำเป็น
6. **Security** — ป้องกันการเข้าถึงโดยไม่ได้รับอนุญาต
7. **Accountability** — ต้องแสดงความรับผิดชอบ

**ฐานความชอบด้วยกฎหมาย 6 ประการ (Section 24):**
1. **Consent** — ความยินยอม (ต้องชัดเจน, ถอนได้)
2. **Contract** — การทำสัญญา
3. **Legal Obligation** — กฎหมายบังคับ
4. **Vital Interest** — เพื่อปกป้องชีวิต
5. **Public Task** — ภารกิจของรัฐ
6. **Legitimate Interest** — ผลประโยชน์อันชอบด้วยกฎหมาย

### 3.2 Lawful Basis สำหรับกรณี Sahana Eden

| กรณีการเก็บข้อมูล | Lawful Basis ที่เหมาะสม | หมายเหตุ |
|---|---|---|
| ลงทะเบียนอาสาสมัคร | **Consent** หรือ **Contract** | ถ้าเป็นภาคีเครือของรัฐ → Public Task |
| ทะเบียนผู้ประสบภัย (DVR) | **Vital Interest** + **Public Task** | ในภัยพิบัติ เพื่อช่วยชีวิต |
| ข้อมูลผู้ป่วย (med/patient) | **Vital Interest** + **Consent** (ถ้าไม่ฉุกเฉิน) | sensitive data — ต้อง explicit consent |
| ลงทะเบียนผู้ใช้ระบบ (auth_user) | **Contract** | สัญญาใช้บริการ |
| CMS Posts / Announcements | **Legitimate Interest** | ข้อมูลสาธารณะ ไม่ใช่ PII |
| SMS/Email log (msg_log) | **Legitimate Interest** + Consent (ผู้รับ) | ต้องมี unsubscribe |
| Audit log (auth_event) | **Legal Obligation** | กฎหมายบังคับบันทึก |
| AI chatbot conversation log | **Consent** | ต้องบอกผู้ใช้ว่าเก็บ |

### 3.3 การจัดประเภทข้อมูลส่วนบุคคลใน Eden

ตารางใน Eden ที่มีข้อมูลส่วนบุคคล (ต้องคุ้มครองพิเศษ):

| ตาราง | ข้อมูลส่วนบุคคล | ระดับความอ่อนไหว |
|-------|--------------|----------------|
| `auth_user` | email, first/last_name, password (hashed), organisation_id | ปกติ |
| `auth_user` (ถ้าเพิ่ม) | phone, national_id | **อ่อนไหว** (เลขบัตร) |
| `pr_person` | first/last_name, DOB, address, phone, email | ปกติ + บาง field อ่อนไหว |
| `pr_person` (ถ้าเก็บ health) | blood_type, allergies, conditions | **อ่อนไหวมาก** (health data) |
| `dvr_case` | ข้อมูลผู้ประสบภัีบ, family relations, ID numbers | **อ่อนไหวมาก** |
| `dvr_case_event` | สถานการณ์, การประเมิน, ความพิการ | **อ่อนไหวมาก** |
| `med_patient` | ข้อมูลผู้ป่วย, การวินิจฉัย, การรักษา | **อ่อนไหวมาก** (health) |
| `hms_hospital` | ข้อมูลโรงพยาบาล | ข้อมูลองค์กร (ไม่ใช่ PII) |
| `hrm_human_resource` | ข้อมูลบุคลากร, skill, การฝึกอบรม | ปกติ + บาง field อ่อนไหว |
| `msg_log` | SMS/email content, recipients | อ่อนไหว (content) |
| `cms_post` | ผู้เขียน, เนื้อหา | ปกติ (แต่อย่าลง PII ในโพสต์) |
| `gis_location` | address (บางครั้งเป็นบ้านคน) | ปกติ → อ่อนไหว (ถ้าเป็นบ้านส่วนตัว) |
| `sync_repository` | sync config | ไม่ใช่ PII |
| `ai_chat_log` (ใหม่) | คำถามผู้ใช้, IP | ปกติ + อาจมี PII ถ้า user พิมพ์มา |

### 3.4 Consent Management

#### 3.4.1 ระบบจัดเก็บ Consent

สร้างตาราง `consent_record` (ใหม่):

```python
# ใน models/00_tables.py
db.define_table("consent_record",
    Field("person_id", "reference pr_person"),  # เจ้าของข้อมูล
    Field("purpose", "string"),  # "volunteer_registration", "patient_treatment", "data_sharing"
    Field("lawful_basis", "string"),  # "consent", "vital_interest", "public_task"
    Field("consent_given", "boolean", default=False),
    Field("consent_text", "text"),  # ข้อความที่ user เห็นตอนให้ consent (versioned)
    Field("consent_version", "string"),  # e.g. "consent-v1.2-2026"
    Field("consent_date", "datetime"),
    Field("withdrawal_date", "datetime"),  # NULL = ยังไม่ถอน
    Field("withdrawal_reason", "text"),
    Field("collected_by", "reference auth_user"),  # ใครเก็บ consent
    Field("signature_image", "upload"),  # ลายเซ็น (ถ้ามี)
    Field("evidence", "text"),  # IP, user-agent, screenshot URL
    Field("uuid", "string"),
    # S3 base fields
    *s3base_fields(),
)
```

#### 3.4.2 แบบฟอร์ม Consent ตัวอย่าง (สำหรับอาสาสมัคร)

```
ข้อตกลงการเก็บข้อมูลอาสาสมัคร (Consent Form v1.2)

องค์กร [ชื่อ org] จะเก็บข้อมูลของท่านเพื่อวัตถุประสงค์ดังนี้:
1. ลงทะเบียนเป็นอาสาสมัครในระบบ Sahana Eden
2. ติดต่อท่านเพื่อประสานงานในเหตุฉุกเฉิน
3. บันทึกประวัติการเข้าร่วมกิจกรรม

ข้อมูลที่เก็บ: ชื่อ-นามสกุล, เบอร์โทร, email, ทักษะ, องค์กรที่สังกัด
ระยะเวลาเก็บ: 5 ปีนับจากวันลงทะเบียน
สิทธิของท่าน: ตรวจสอบ, แก้ไข, ลบ, ถอนความยินยอมได้ตลอดเวลา

ข้าพเจ้ายินยอมให้เก็บและใช้ข้อมูลตามข้อตกลงนี้
[ ] ยินยอม   [ ] ไม่ยินยอม

ลงชื่อ: ____________________  วันที่: __________
```

#### 3.4.3 Implementation ใน Eden

```python
# ใน controllers/hrm.py
@auth.requires_login()
def register_volunteer():
    form = SQLFORM(db.auth_user)
    if form.accepts(request.vars, session):
        # บันทึก consent
        db.consent_record.insert(
            person_id=created_person_id,
            purpose="volunteer_registration",
            lawful_basis="consent",
            consent_given=True,
            consent_text=CONSENT_TEXT_V12,
            consent_version="consent-v1.2-2026",
            consent_date=request.now,
            collected_by=auth.user.id,
            evidence=f"IP={request.env.remote_addr}; UA={request.env.http_user_agent}",
        )
        # ส่ง email ยืนยัน + copy ของ consent
        send_consent_email(form.vars.email, CONSENT_TEXT_V12)
```

### 3.5 Data Subject Rights Implementation

PDPA Section 30-37 ให้สิทธิผู้ถูกเก็บข้อมูล 8 ประการ:

| สิทธิ | Section | การ implement ใน Eden |
|------|---------|---------------------|
| แจ้งเก็บข้อมูล | 30, 31 | Notification modal ตอน register + อีเมลยืนยัน |
| เข้าถึงข้อมูล | 32 | `/eden/default/user/my_data` — export ข้อมูลตัวเองเป็น JSON |
| แก้ไขข้อมูล | 33 | `/eden/pr/person/edit/[own_id]` (มีอยู่แล้ว) |
| ลบข้อมูล | 34 | `/eden/default/user/delete_my_data` — soft delete + ลบจริงหลัง 90 วัน |
| จำกัดการประมวลผล | 35 | flag `processing_restricted=True` ใน `auth_user` |
| ถอนความยินยอม | 19 | `/eden/default/user/withdraw_consent` |
| ส่งต่อข้อมูล | 36 | Export เป็น JSON (machine-readable) |
| คัดค้าน | 37 | form ส่งเรื่อง + DPO ตรวจภายใน 30 วัน |

```python
# controllers/default.py — เพิ่ม function
def my_data():
    """ส่งออกข้อมูลส่วนบุคคลทั้งหมดของ user ปัจจุบัน (สิทธิเข้าถึงข้อมูล + ส่งต่อ)"""
    if not auth.user:
        redirect(URL("default", "user/login"))
    user_id = auth.user.id
    data = {
        "auth_user": db.auth_user(user_id).as_dict(),
        "pr_person": db(db.pr_person_user.user_id == user_id).select().first().as_dict() if ... else None,
        "hrm_human_resource": db(db.hrm_human_resource.person_id == person_id).select().as_list(),
        "consent_records": db(db.consent_record.person_id == person_id).select().as_list(),
        "auth_event": db(db.auth_event.user_id == user_id).select().as_list(),
    }
    # export เป็น JSON ให้ download
    response.headers["Content-Type"] = "application/json"
    response.headers["Content-Disposition"] = f'attachment; filename="my_data_{user_id}_{request.now}.json"'
    return json.dumps(data, indent=2, default=str)
```

### 3.6 Data Minimization

**หลักการ:** เก็บเฉพาะที่จำเป็น — อย่าเก็บ "เผื่อไว้"

**การปรับใน Eden:**

1. ลบ field ที่ไม่ใช้ใน `auth_user` (เช่น `comments`, `timestmp`) หรืออย่า populate ใน form
2. ใน form สมัครอาสาสมัคร — เก็บแค่ first_name, last_name, email, phone (ถ้าจำเป็น), skill → อย่าเก็บ DOB, address, ฯลฯ ถ้าไม่ใช้
3. Default form ของ `pr_person` มี ~30 field — ซ่อน field ที่ไม่จำเป็นด้วย `settings.ui.hidden_fields`
4. SMS/email content ใน `msg_log` — เก็บแค่ metadata (sender, recipient, timestamp) ไม่เก็บ content ถ้าไม่จำเป็น

### 3.7 Retention Policy

กำหนดระยะเก็บข้อมูลแต่ละประเภท:

| ประเภทข้อมูล | ระยะเก็บ | เหตุผล | วิธีลบ |
|---|---|---|---|
| อาสาสมัคร (auth_user + pr_person) | 5 ปีหลัง last activity | ใช้งานต่อเนื่อง | Anonymize (เปลี่ยน name เป็น "ANONYMIZED") |
| ผู้ประสบภัย (dvr_case) | 10 ปี | กฎหมาย (ถ้าเกี่ยวกับคดี) | ลบ hard หลังหมดอายุความ |
| ผู้ป่วย (med_patient) | 10 ปี (มาตรฐานการแพทย์) | กฎกระทรวงสาธารณสุข | Encrypt + archive ใน cold storage |
| CMS post | ไม่จำกัด (ข้อมูลสาธารณะ) | ประวัติศาสตร์ | ไม่ลบ |
| msg_log (SMS/email content) | 90 วัน | ตรวจสอบ issue | Auto-delete |
| auth_event (audit log) | 3 ปี | Security + compliance | Auto-delete |
| ai_chat_log | 90 วัน | ปรับปรุง chatbot | Auto-delete |
| consent_record | ตลอดอายุการเก็บข้อมูล + 3 ปี | พิสูจน์ consent | ลบหลังข้อมูลที่เกี่ยวข้องถูกลบ |

**Implementation:**
```python
# scheduler task รายเดือน
def data_retention_cleanup():
    """ลบ/expired ข้อมูลที่หมด retention period"""
    now = request.now
    # msg_log > 90 วัน
    db(db.msg_log.created_on < now - timedelta(days=90)).delete()
    # ai_chat_log > 90 วัน
    db(db.ai_chat_log.created_on < now - timedelta(days=90)).delete()
    # auth_event > 3 ปี
    db(db.auth_event.time_stamp < now - timedelta(days=365*3)).delete()
    # volunteer ไม่ active > 5 ปี → anonymize
    inactive_users = db(
        (db.auth_user.modified_on < now - timedelta(days=365*5)) &
        (db.auth_user.deleted == False)
    ).select()
    for u in inactive_users:
        u.update_record(
            first_name="ANONYMIZED",
            last_name="ANONYMIZED",
            email=f"anonymized-{u.id}@invalid.local",
            password="!anonymized!",
            registration_key="blocked",
        )
```

### 3.8 Cross-Border Data Transfer

PDPA Section 28-29 ห้ามส่งข้อมูลส่วนบุคคลออกนอกประเทศ ยกเว้น:
1. ปลายทางมีกฎหมายคุ้มครองเทียบเท่า PDPA (เช่น EU GDPR)
2. มี Standard Contractual Clauses (SCC)
3. BCR (Binding Corporate Rules)
4. ได้ consent จากเจ้าของข้อมูล

**กรณี Sahana Eden:**
- ถ้า deploy บน AWS/Azure/GCP region นอกไทย (เช่น Singapore, US-East) → ต้องตรวจ
- ถ้าใช้ Gmail SMTP → email ผ่านเซิร์ฟเวอร์ Google (ส่วนใหญ่ใน US) → ต้องได้ consent
- ถ้าใช้ AI API (OpenAI, Anthropic) → ข้อมูลที่ส่งไป train/prompt → **ควรใช้ zero-retention tier** (OpenAI's API ไม่เก็บข้อมูล train)
- แนะนำ: deploy บน Thai cloud (CAT Telecom, True IDC) หรือ on-premise เพื่อหลีกเลี่ยงปัญหา

### 3.9 Data Protection Officer (DPO)

PDPA Section 41 กำหนดให้แต่งตั้ง DPO ถ้า:
- เป็น public authority
- ทำกิจกรรมที่ต้องเฝ้าระวังตามกฎกระทรวง
- เก็บ/ใช้ข้อมูลส่วนบุคคลจำนวนมาก

**สำหรับ Sahana Eden ในไทย:** ถ้า deploy โดยหน่วยงานรัฐ (DDPM, กู้ภาย) → ต้องมี DPO

**หน้าที่ DPO:**
1. ให้คำแนะนำด้าน PDPA แก่องค์กร
2. ตรวจสอบการปฏิบัติตาม
3. เป็นจุดติดต่อกับ PDPC (Personal Data Protection Committee)
4. จัดการ data subject requests
5. รายงาน breach ภายใน 72 ชม.

**ใน Eden:** เพิ่ม role `DPO` ใน `auth_group`:
```python
db.auth_group.insert(uuid="DPO", role="Data Protection Officer")
# ให้สิทธิ DPO เฉพาะ module admin/dpo
```

### 3.10 Breach Notification (72 ชม.)

PDPA Section 75 กำหนด: หากเกิด data breach ต้องแจ้ง PDPC **ภายใน 72 ชั่วโมง** หลังรู้

**Breach response plan:**
1. **Detect:** SIEM alert หรือ user report
2. **Contain:** disable compromised accounts, block IP
3. **Assess:** ข้อมูลอะไรรั่ว? กี่คน? ระดับความอ่อนไหว?
4. **Notify PDPC:** ภายใน 72 ชม. — ใช้แบบฟอร์มจาก pdpa.or.th
5. **Notify data subjects:** ถ้าเป็น high-risk breach (sensitive data)
6. **Document:** บันทึกทุกขั้นตอน (post-mortem)

**Tooling:**
- Incident response template (Thai + English)
- Pre-filled PDPC notification form
- Communication template สำหรับ affected users

```python
# controllers/admin.py
@auth.requires_membership("DPO")
def incident_breach():
    """form สำหรับบันทึก + แจ้ง data breach"""
    form = SQLFORM(db.data_breach_incident)
    if form.accepts(request.vars):
        # ส่งอีเมลแจ้ง DPO + ผู้บริหาร
        send_breach_notification(form.vars)
        # แจ้งเตือนให้ DPO เตรียมไฟล์ PDPC ภายใน 72 ชม.
        if not breach_reported_to_pdpc(form.vars.id):
            schedule_reminder(72*60)  # 72 ชม.
```

### 3.11 Privacy by Design

PDPA Section 19 — Privacy by Design ต้องฝังในกระบวนการพัฒนา:

1. **Privacy Impact Assessment (PIA)** ก่อนพัฒนาฟีเจอร์ใหม่:
   - ฟีเจอร์เก็บข้อมูลอะไร?
   - จำเป็นขนาดไหน?
   - ใครเข้าถึง?
   - เก็บนานแค่ไหน?
2. **Default settings:** ปิด data collection ที่ไม่จำเป็น default (opt-in ไม่ opt-out)
3. **Pseudonymization:** ถ้าเป็นไปได้ ใช้ ID แทนชื่อจริงในระบบ internal
4. **Data segregation:** ข้อมูล sensitive แยก table + separate encryption key

### 3.12 Children's Data

PDPA Section 26 — ข้อมูลเด็ก (< 10 ปี) ต้องได้ consent จากผู้ปกครอง

**ใน Sahana Eden:**
- โมดูล `dvr_case` อาจเก็บข้อมูลเด็กที่ประสบภัย → ต้องเก็บ parent/guardian consent
- โมดูล `med_patient` สำหรับเด็ก → ต้องมี field `parent_guardian_id`
- หากเด็ก > 10 ปี ให้ consent เองได้ แต่แนะนำให้ขอ parent consent ด้วยในกรณี sensitive

### 3.13 Data Processing Agreement (DPA)

ถ้าใช้ vendor ภายนอก (cloud, SaaS, AI API) ต้องมี DPA:
- **Cloud (AWS/Azure):** มี DPA template สำเร็จ
- **AI API (OpenAI/Anthropic):** ต้องเช็คว่าใช้ข้อมูล train ไหม → เลือก zero-retention
- **Line/Facebook Messenger** (ถ้าเชื่อม chatbot): ต้องอ่าน policy + ทำ DPA
- **Gmail SMTP:** Google มี DPA สำหรับ Workspace → แนะนำใช้ Workspace ไม่ใช่ free Gmail

---

## ภาคที่ 4: Roadmap การปรับปรุงแบ่งตามระยะ

### ระยะที่ 1: Quick Wins (1-3 เดือน)

| ลำดับ | รายการ | มิติ | ความยาก | ผลกระทบ |
|------|--------|-----|--------|--------|
| 1 | ปิด debug mode ใน production | Security | ง่าย | สูง |
| 2 | เปลี่ยน hmac_key เป็น random 64 bytes | Security | ง่าย | สูง |
| 3 | ตั้ง Gmail App Password จริง | Email | ง่าย | สูง |
| 4 | ลบ `welcome` app + ตั้ง `eden` เป็น default | Security | ง่าย | กลาง |
| 5 | เพิ่ม HTTP security headers ที่ Caddy | Security | ง่าย | สูง |
| 6 | ปิด TLS 1.0/1.1 ที่ Caddy | Security | ง่าย | สูง |
| 7 | รัน `pip-audit` + อัปเดต dependencies | Security | ง่าย | กลาง |
| 8 | เขียน Privacy Notice สำหรับ user | PDPA | ง่าย | สูง |
| 9 | ตั้ง password policy 12+ ตัว + complexity | Security | ง่าย | กลาง |
| 10 | เปิด audit log สำหรับ sensitive tables | PDPA + Security | กลาง | สูง |
| 11 | ปิด `.csv`/`.xls` export สำหรับ user ที่ไม่มีสิทธิ์ | Security + PDPA | กลาง | กลาง |
| 12 | สำรอง DB nightly + test restore | Security | กลาง | สูง |

### ระยะที่ 2: Medium Term (3-6 เดือน)

| ลำดับ | รายการ | มิติ | ความยาก | ผลกระทบ |
|------|--------|-----|--------|--------|
| 13 | เปิด 2FA บังคับสำหรับ ADMIN | Security | กลาง | สูงมาก |
| 14 | Column-level encryption สำหรับ sensitive fields | Security + PDPA | กลาง | สูงมาก |
| 15 | สร้าง consent_record table + workflow | PDPA | กลาง | สูงมาก |
| 16 | Data subject rights: my_data export, withdraw_consent | PDPA | กลาง | สูง |
| 17 | สร้าง AI chatbot สำหรับ public Q&A (RAG) | AI | กลาง | สูง |
| 18 | AI OCR สำหรับบัตรประชาชน + auto-fill form | AI | กลาง | สูง |
| 19 | ปรับ session timeout 30 นาที + SameSite=Strict | Security | ง่าย | กลาง |
| 20 | Rate limiting ที่ API | Security | กลาง | กลาง |
| 21 | SIEM integration (Wazuh/ELK) | Security | กลาง | สูง |
| 22 | ทำ retention policy + scheduler cleanup | PDPA | กลาง | สูง |
| 23 | Penetration test ครั้งแรก | Security | ง่าย (จ้าง) | สูงมาก |

### ระยะที่ 3: Long Term (6-12 เดือน)

| ลำดับ | รายการ | มิติ | ความยาก | ผลกระทบ |
|------|--------|-----|--------|--------|
| 24 | Migrate จาก SQLite → PostgreSQL + PostGIS | Architecture | กลาง | สูงมาก |
| 25 | เปลี่ยน mail server เป็น on-prem (หลีกเลี่ยง Gmail cross-border) | PDPA | กลาง | กลาง |
| 26 | AI predictive analytics สำหรับ inventory + shelter | AI | ยาก | สูง |
| 27 | AI image recognition สำหรับ satellite imagery | AI | ยาก | สูงมาก |
| 28 | SSO (OIDC) ผ่าน Keycloak / Azure AD | Security | ยาก | สูง |
| 29 | Docker + Kubernetes deployment + CI/CD | DevOps | ยาก | สูง |
| 30 | Voice interface (Whisper STT + TTS) | AI | กลาง | กลาง |
| 31 | แต่งตั้ง DPO + ทำ PIA สำหรับทุก module | PDPA | กลาง | สูงมาก |
| 32 | PDPA audit โดยบริษัทภายนอก | PDPA | ง่าย (จ้าง) | สูงมาก |
| 33 | สร้าง SBOM + sign releases | Security | กลาง | กลาง |

---

## ภาคที่ 5: สรุปและลำดับความสำคัญ

### 5.1 Top 5 สิ่งที่ควรทำก่อน (ถ้าทำได้แค่ 5 อย่าง)

1. **ปิด debug mode + เปลี่ยน hmac_key + ตั้ง password จริง** — ลดช่องโหว่เบื้องต้น
2. **ตั้ง HTTP security headers + บังคับ TLS 1.3** — กัน man-in-the-middle
3. **สร้าง Privacy Notice + consent workflow** — พื้นฐาน PDPA
4. **เปิด audit log + สำรองข้อมูล nightly** — ความรับผิดชอบ + recoverability
5. **ตั้ง 2FA บังคับสำหรับ admin** — กัน unauthorized admin access

### 5.2 Top 3 AI use cases ที่คุ้มที่สุด

1. **AI Chatbot สำหรับประชาชน (RAG)** — ลดภาระ call center, ตอบด่วน 24/7
2. **AI OCR สำหรับบัตรประชาชน** — เร่ง data entry ในสนาม, ลดความผิดพลาด
3. **AI Translation สำหรับภาษาไทย** — อัปเดต translation files อัตโนมัติ

### 5.3 PDPA สิ่งที่ห้ามละเว้น

1. **Privacy Notice** ต้องแสดงก่อนเก็บข้อมูลทุกครั้ง
2. **Consent record** ต้องเก็บ + สามารถถอนได้
3. **Data subject rights** ต้อง implement อย่างน้อย: เข้าถึง + ลบ + ถอน consent
4. **Breach notification** ต้องมี plan + ติดต่อ PDPC ภายใน 72 ชม.
5. **DPO** ถ้าเป็นหน่วยงานรัฐ

### 5.4 ข้อจำกัดที่ต้องรับทราบ

- **web2py framework:** ไม่ใช่ modern framework (เทียบกับ FastAPI, Next.js) — อัปเดตน้อย, community เล็ก
- **AI integration:** ต้องระวัง PDPA โดยเฉพาะ data ที่ส่งให้ LLM (ใช้ zero-retention API)
- **PDPA:** กฎหมายใหม่ — มี case law น้อย → ตีความ conservative ไว้ก่อน
- **Thai language support:** ใน Eden มีอยู่แล้ว แต่ translation files ต้องดูแลต่อเนื่อง

---

## ภาคผนวก: อ้างอิง

### AI
- Z.ai API: https://z.ai
- OpenAI API: https://platform.openai.com
- LangChain: https://python.langchain.com
- Whisper (STT): https://github.com/openai/whisper
- PyThaiNLP: https://pythainlp.github.io

### Cyber Security
- OWASP Top 10 (2021): https://owasp.org/Top10
- OWASP ASVS (Application Security Verification Standard): https://owasp.org/www-project-application-security-verification-standard
- NIST Cybersecurity Framework: https://www.nist.gov/cyberframework
- CIS Controls: https://www.cisecurity.org/controls

### PDPA (Thailand)
- พ.ร.บ. คุ้มครองข้อมูลส่วนบุคคล พ.ศ. 2562: https://www.ratchakitcha.soc.go.th
- คณะกรรมการคุ้มครองข้อมูลส่วนบุคคล (PDPC): https://www.pdpc.or.th
- คู่มือ PDPA สำหรับองค์กรภาครัฐ: https://www.pdpc.or.th/download/...

### Sahana Eden
- Documentation: https://eden-asp.readthedocs.io
- Wiki: https://eden.sahanafoundation.org
- GitHub: https://github.com/sahana/eden

---

*เอกสารฉบับนี้จัดทำเมื่อ 2026-11-18 สำหรับ Sahana Eden v6.2 บน web2py 3.3.3 — คำแนะนำเป็น general guidance ควรปรับใช้ตามบริบทเฉพาะขององค์กรและปรึกษาผู้เชี่ยวชาญด้าน PDPA ก่อน deploy จริง*
