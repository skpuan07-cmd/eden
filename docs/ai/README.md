# AI Modules for Sahana Eden — คู่มือ 10 Use Cases

แพ็คเกจนี้ประกอบด้วย AI controllers ทั้ง 10 ที่แนะนำในเอกสาร RECOMMENDATIONS.md ภาคที่ 1 — พร้อมโค้ด คำอธิบาย และวิธีใช้งาน

## ข้อกำหนดเบื้องต้น

1. **z-ai-web-dev-sdk** ติดตั้งและ CLI `z-ai` อยู่ใน PATH
2. **Sahana Eden** ที่ติดตั้งและรันทำงานได้
3. Python dependencies:
   ```bash
   pip install --break-system-packages prophet pandas   # สำหรับ Use Case 3 (Predictive Analytics)
   ```
4. (ถ้าต้องการ vector search จริง) **PostgreSQL + pgvector** + `pip install openai` สำหรับ embeddings

## การติดตั้ง

### 1. วางไฟล์ในโฟลเดอร์ Eden

```bash
# สมมติ Eden อยู่ที่ ~/eden และ web2py อยู่ที่ ~/web2py
cp controllers/*.py                          ~/eden/controllers/
cp models/ai_tables.py                       ~/eden/models/
cp modules/s3/ai_client.py                   ~/eden/modules/s3/
cp -r views/ai_*                             ~/eden/views/

# ให้สิทธิ์ web2py เขียนโฟลเดอร์ TTS
mkdir -p ~/eden/uploads/ai_voice
chown www-data:www-data ~/eden/uploads/ai_voice
```

### 2. Restart web2py

```bash
kill -TERM $(cat ~/eden-logs/web2py.pid)
python3 ~/scripts/launch_eden_daemon.py
```

### 3. ตรวจสอบตาราง AI ถูกสร้าง

เปิด: `http://127.0.0.1:3000/eden/default/index` → login เป็น admin → ไปที่ `appadmin` → ดู `ai_*` tables

---

## Use Case 1: AI Chatbot (RAG) — `controllers/ai_chat.py`

### คำอธิบาย
Chatbot สำหรับประชาชนและอาสาสมัคร ตอบคำถามเกี่ยวกับภัยพิบัติ โดยดึง context จาก knowledge base (ตาราง `ai_knowledge_chunk`) ก่อนเรียก LLM (RAG pattern)

### วิธีใช้
1. **Index knowledge base ก่อน** — ไปที่ `/eden/ai_kb/ingest_cms_posts` เพื่อ index CMS posts ที่เป็น public
2. **เปิด chat UI** — `/eden/ai_chat/`
3. **PDPA consent** — ผู้ใช้ต้องกด "I agree" ก่อนเริ่มสนทนา
4. **ถามคำถาม** — เช่น "ศูนย์พักพิงใกล้ฉันอยู่ที่ไหน?" หรือ "เบอร์ติดต่อ DDPM คืออะไร?"
5. **Rate answer** — กด 👍/👎 เพื่อให้ feedback

### Endpoints
| URL | Method | คำอธิบาย |
|-----|--------|---------|
| `/eden/ai_chat/` | GET | Chat UI |
| `/eden/ai_chat/ask` | POST | ส่งคำถาม → รับคำตอบ (JSON) |
| `/eden/ai_chat/history` | GET | ประวัติการสนทนาของ user |
| `/eden/ai_chat/rate` | POST | Rate answer (+1/-1) |
| `/eden/ai_chat/clear` | POST | เคลียร์ session |
| `/eden/ai_chat/widget` | GET | Embeddable widget (iframe) |
| `/eden/ai_chat/consent` | GET | Privacy notice |

### PDPA compliance
- บันทึก consent ใน session ก่อนเก็บ chat log
- chat log เก็บใน `ai_chat_log` พร้อม `consent_given` flag
- 90 วัน auto-delete (ตาม retention policy)
- ห้าม embedding ข้อมูล sensitive ใน knowledge base

### ตัวอย่าง API call
```bash
curl -X POST https://preview-chat-XXX.space-z.ai/eden/ai_chat/ask \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -b cookies.txt \
  --data-urlencode "question=ศูนย์พักพิงในเชียงรายอยู่ที่ไหน?"
```

---

## Use Case 2: AI OCR + Data Extraction — `controllers/ai_ocr.py`

### คำอธิบาย
อัปโหลดรูปเอกสาร (บัตรประชาชน, ใบเบิก, แบบฟอร์มศูนย์พักพิง, รายงานผู้ประสบภัย) → vision model ดึงข้อมูลเป็น structured JSON → ใช้ pre-fill form ใน Eden

### ประเภทเอกสารที่รองรับ
| document_type | ใช้กับ |
|---------------|-------|
| `id_card` | บัตรประชาชนไทย → pre-fill `auth_user` / `pr_person` |
| `invoice` | ใบเบิกวัสดุ → pre-fill `inv_inv_item` |
| `shelter_form` | แบบฟอร์มศูนย์พักพิง → pre-fill `cr_shelter` |
| `victim_report` | รายงานผู้ประสบภัย → pre-fill `dvr_case` (sensitive!) |

### PDPA compliance
- ต้องได้ consent จากเจ้าของข้อมูลก่อน
- รูปภาพถูกลบหลัง extraction (เก็บแค่ JSON output)
- extracted_data เข้ารหัสที่ at-rest (ถ้าเปิด column encryption)
- log ทุก job ใน `ai_ocr_job` พร้อม `consent_given` flag

### ตัวอย่าง
```bash
curl -X POST https://preview-chat-XXX.space-z.ai/eden/ai_ocr/extract \
  -F "document_type=id_card" \
  -F "consent=yes" \
  -F "file=@/path/to/id_card.jpg"
```

---

## Use Case 3: AI Predictive Analytics — `controllers/ai_analytics.py`

### คำอธิบาย
ใช้ Facebook Prophet ทำนาย time series 30 วันข้างหน้า สำหรับ:
- **inventory_demand** — ความต้องการสินค้ารายวัน (จาก `inv_inv_track`)
- **shelter_occupancy** — จำนวนคนในศูนย์พักพิง (จาก `sit_presence`)
- **incident_count** — จำนวนเหตุการณ์รายวัน (จาก `cms_post`)

### การติดตั้ง dependencies
```bash
pip install --break-system-packages prophet pandas
```

### วิธีใช้
1. ไปที่ `/eden/ai_analytics/run/inventory_demand` (admin)
2. รอสักครู่ (fit 30 วินาที - 2 นาที)
3. ดู chart ที่ `/eden/ai_analytics/forecast/inventory_demand`
4. ดู data ที่ `/eden/ai_analytics/data/inventory_demand.json` (สำหรับ Chart.js)

### Scheduler integration
เพิ่มใน `models/tasks.py`:
```python
def forecast_all():
    """รันทุกคืน 02:00"""
    from gluon import current
    current.manager.current_controller = "ai_analytics"
    for target in ["inventory_demand", "shelter_occupancy", "incident_count"]:
        current.manager.run(target)
```

---

## Use Case 4: AI Image Recognition — `controllers/ai_imagery.py`

### คำอธิบาย
อัปโหลดภาพถ่าย (ดาวเทียม/drone/ภาคพื้น) → vision model วิเคราะห์:
- **flood_extent** — ตรวจจับขอบเขตน้ำท่วม
- **building_damage** — จำแนกระดับความเสียหายอาคาร (minor/moderate/severe/destroyed)
- **road_passability** — ตรวจสอบถนนที่ผ่านได้/ไม่ได้
- **general** — คำอธิบายภาพทั่วไป + tags

### วิธีใช้
1. `/eden/ai_imagery/` → upload UI
2. เลือก analysis_type + อัปโหลดภาพ
3. รับ JSON ผลลัพธ์ + สรุปภาษาไทยอัตโนมัติ

### Integration กับ GIS
- สามารถระบุ `location_id` เพื่อผูกกับ `gis_location` ใน Eden
- ผลลัพธ์เก็บใน `ai_imagery_job` พร้อม `result_json` + `result_summary`

---

## Use Case 5: AI Translation — `controllers/ai_translate.py`

### คำอธิบาย
ช่วย admin แปล UI strings จาก `languages/en.py` เป็นภาษาอื่น (เช่น `th.py`) โดยอัตโนมัติ พร้อม review queue ก่อน apply

### Workflow
1. `/eden/ai_translate/` → เลือกภาษา
2. `/eden/ai_translate/missing/th` → ดู strings ที่ยังไม่แปล
3. เลือก strings → กด "Batch translate" → เข้า review queue
4. `/eden/ai_translate/review?lang=th` → reviewer ตรวจ + แก้ไข
5. Approve ทีละรายการ
6. `/eden/ai_translate/apply_approved?lang=th` → เขียนกลับ `languages/th.py`

### PDPA note
ไม่มีข้อมูลส่วนบุคคล — เป็นเพียง UI text strings จึงไม่ต้องขอ consent

---

## Use Case 6: AI Natural Language Query — `controllers/ai_query.py`

### คำอธิบาย
แปลงคำถามภาษาธรรมดา ("แสดงศูนย์พักพิงในเชียงรายที่รองรับได้มากกว่า 100 คน") เป็น Eden REST API URL → execute → format คำตอบเป็นภาษาไทย

### Whitelist (PDPA safety)
อนุญาตเฉพาะ controllers:
- `org/organisation`, `org/office`, `org/site`
- `cr/shelter`
- `inv/warehouse`, `inv/inv_item`
- `project/project`
- `cms/post`
- `gis/location`
- `hrm/human_resource`
- `req/req`
- `stats/index`

**ห้าม query** ข้อมูล sensitive (`auth_user`, `dvr_case`, `med_patient`, `msg_log`) ผ่าน NLQ

### วิธีใช้
1. `/eden/ai_query/` (admin only) → พิมพ์คำถาม
2. รับ: คำตอบภาษาไทย + API URL + จำนวนผลลัพธ์ + 5 ตัวอย่างแรก
3. ประวัติ query ทั้งหมดเก็บใน `ai_query_log`

---

## Use Case 7: AI Code Assistance (เอกสารเท่านั้น)

ไม่ใช่ฟีเจอร์ใน Eden แต่เป็นคำแนะนำสำหรับทีมพัฒนา — ดู `docs/CODE_ASSISTANCE.md`

---

## Use Case 8: RAG Knowledge Base — `controllers/ai_kb.py`

### คำอธิบาย
Admin UI สำหรับจัดการ knowledge base ที่ chatbot (Use Case 1) ใช้:
- Index CMS posts → chunks
- Index external URLs (wiki, docs)
- Browse / edit / delete chunks
- Rebuild vector index (placeholder สำหรับ pgvector upgrade)

### Endpoints
| URL | คำอธิบาย |
|-----|---------|
| `/eden/ai_kb/` | dashboard พร้อม stats |
| `/eden/ai_kb/ingest_cms_posts` | index CMS posts ทั้งหมด |
| `/eden/ai_kb/ingest_url` (POST) | fetch URL + index |
| `/eden/ai_kb/list_chunks` | browse chunks |
| `/eden/ai_kb/chunk/<id>` | view/edit |
| `/eden/ai_kb/delete/<id>` | soft delete |
| `/eden/ai_kb/rebuild_index` | re-embed (placeholder) |

---

## Use Case 9: AI Voice Interface — `controllers/ai_voice.py`

### คำอธิบาย
Voice interface สำหรับอาสาสมัครในสนาม:
- `/eden/ai_voice/transcribe` — อัปโหลดเสียง → text (ASR)
- `/eden/ai_voice/speak` — text → เสียง (TTS)
- `/eden/ai_voice/command` — วงรอบเต็ม: เสียง → text → intent → reply text → reply เสียง

### เสียงที่รองรับ
- Input: WAV, MP3 (ส่งให้ z-ai ASR)
- Output: WAV (default), MP3, PCM

### ภาษา
- ASR: auto-detect (รองรับภาษาไทย)
- TTS: voice `tongtong` (default), speed 0.5-2.0

---

## Use Case 10: AI Content Moderation — `controllers/ai_moderation.py`

### คำอธิบาย
Auto-moderate user-submitted content (CMS posts, chat messages) ก่อน publish:
- ตรวจ 8 หมวด: hate, harassment, self_harm, sexual, violence, spam, misinformation, **pdpa_violation**
- Auto-action: high score → blocked, medium → flagged, low → published
- Review queue สำหรับ admin

### PDPA violation detection
- ตรวจหาเลขบัตรประชาชน 13 หลัก
- ตรวจหาเบอร์มือถือไทย (08x/09x)
- ตรวจหา personal IDs อื่นๆ

### Integration hooks
เพิ่มใน `controllers/cms.py` หลัง post creation:
```python
def post():
    form = crud.create(db.cms_post)
    if form.accepted:
        from gluon import current
        current.manager.current_controller = "ai_moderation"
        current.manager.run("moderate_cms_post", args=[form.vars.id])
```

---

## Database Tables ที่เพิ่มใหม่

ตารางทั้งหมดถูกสร้างโดย `models/ai_tables.py` เมื่อ web2py restart:

| ตาราง | ใช้กับ Use Case |
|-------|---------------|
| `ai_chat_log` | 1 (chatbot) |
| `ai_knowledge_chunk` | 1, 8 (RAG) |
| `ai_ocr_job` | 2 (OCR) |
| `ai_forecast` | 3 (analytics) |
| `ai_imagery_job` | 4 (satellite) |
| `ai_translation_job` | 5 (translation) |
| `ai_query_log` | 6 (NLQ) |
| `ai_voice_log` | 9 (voice) |
| `ai_moderation_queue` | 10 (moderation) |

---

## Security & PDPA Compliance

### Authentication
- Use Cases 2-10 บาง action ต้องการ `auth.has_membership("ADMIN")`
- Use Case 1 (chatbot) เปิดให้ anonymous ได้ แต่ต้อง PDPA consent
- Use Case 6 (NLQ) admin-only เพราะ query ข้อมูล

### Rate limiting
- Chatbot: 60 requests/minute/IP
- NLQ: implicit (admin-only)
- อื่นๆ: web server level (Caddy/nginx)

### PDPA consent
- Use Case 1: บังคับ consent ก่อนเริ่มสนทนา
- Use Case 2: บังคับ consent ก่อน OCR (ข้อมูลในรูปอาจเป็น sensitive)
- Use Cases 3-10: ไม่เก็บ PII โดยตรง (admin operations)

### Retention
- `ai_chat_log`: 90 วัน
- `ai_voice_log`: 90 วัน
- `ai_query_log`: 1 ปี
- `ai_ocr_job`: 1 ปี (audit trail)
- `ai_moderation_queue`: 3 ปี
- `ai_forecast`: ทับด้วย version ใหม่

---

## Troubleshooting

### "z-ai CLI not found"
ติดตั้ง z-ai-web-dev-sdk:
```bash
npm install -g z-ai-web-dev-sdk
# หรือใช้ path เต็มใน modules/s3/ai_client.py
```

### "Vision call timed out"
เพิ่ม timeout ใน `ai_client.py`:
```python
client = AIClient(timeout=300)  # เพิ่มจาก 120 เป็น 300
```

### "Prophet not installed"
```bash
pip install --break-system-packages prophet pandas
```

### Tables ไม่ถูกสร้าง
ตรวจสอบสิทธิ์ SQLite file:
```bash
ls -la ~/eden/databases/storage.db
chown www-data:www-data ~/eden/databases/storage.db
```

### หน้าจอ error หลัง restart
ดู error ticket:
```bash
ls -lt ~/eden/errors/ | head -5
```

---

*เอกสารฉบับนี้จัดทำเมื่อ 2026-11-18 สำหรับ AI modules v1.0 — ใช้กับ Eden v6.2 บน web2py 3.3.3*

## Use Case 11: AI Menu Integration (landing page)

### คำอธิบาย
หน้า landing page `/eden/ai/` เป็นจุดเข้าใช้งานเดียวสำหรับ AI modules ทั้งหมด — แสดงการ์ด 9 ฟีเจอร์พร้อมคำอธิบายและลิงก์เข้าใช้งาน

### การติดตั้ง

1. **วาง controller** `controllers/ai.py` ลงใน Eden
2. **วาง view** `views/ai/index.html`
3. **แก้ `modules/templates/default/config.py`** — เพิ่ม module registration (ดู `config_patch.py` ในแพ็คเกจ):
```python
        ("ai", Storage(
            name_nice = T("AI Assistant"),
            module_type = 7,    # 7th item in the menu
        )),
```
4. **Restart web2py**

หลัง restart จะเห็นเมนู "AI Assistant" ในแถบนำทางหลักของ Eden (ระหว่าง "Map" กับ "more")

### สิ่งที่จะเห็นในหน้า landing
- การ์ด 9 ฟีเจอร์พร้อมไอคอน ชื่อ คำอธิบาย และ badge "PUBLIC"/"ADMIN"
- ลิงก์ "Open →" สำหรับเข้าใช้แต่ละ feature
- ส่วน "About the AI modules" อธิบายเทคโนโลยีที่ใช้

### Endpoints
| URL | Method | Auth | คำอธิบาย |
|-----|--------|------|---------|
| `/eden/ai/` | GET | login required | AI features dashboard (9 cards) |


## AI Panel on Home Page

### คำอธิบาย
แก้ `views/default/index.html` เพื่อเพิ่ม AI panel ที่หน้าแรก (เฉพาะ user ที่ login แล้ว) — เป็น banner สีม่วง gradient พร้อมปุ่ม "เปิดใช้งาน AI" + quick links ไปยังทุก AI feature

### สิ่งที่เพิ่มในไฟล์
- Banner gradient (สีม่วง `#667eea` → `#764ba2`)
- หัวข้อ "AI Assistant" + ไอคอน 🤖
- คำอธิบายสั้นๆ ภาษาไทย
- ปุ่ม "เปิดใช้งาน AI →" → ลิงก์ไป `/eden/ai/`
- Quick links ทั้ง 9 ฟีเจอร์ (Chatbot, OCR, Analytics, Imagery, Voice, Query, Translate, Knowledge, Moderation)

### เงื่อนไขการแสดง
- แสดงเฉพาะเมื่อ user login แล้ว (`AUTHENTICATED in session.s3.roles`)
- ถ้ายังไม่ login จะเห็นแค่ login box (เดิม)

### การติดตั้ง
```bash
cp views/default/index.html ~/eden/views/default/index.html
# Restart web2py
```

