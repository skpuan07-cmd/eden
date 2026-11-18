# Sahana Eden — เอกสารระบบฉบับเต็ม

> เอกสารนี้อธิบาย สถาปัตยกรรมระบบ โครงสร้างฐานข้อมูล การติดตั้งใช้งาน และการปรับปรุงทั้งหมดที่ทำไว้กับ Sahana Eden (web2py) สำหรับการ deploy ในสภาพแวดล้อม sandbox ที่มี Caddy reverse proxy และ external HTTPS URL

---

## สารบัญ

1. [ภาพรวมระบบ](#1-ภาพรวมระบบ)
2. [สถาปัตยกรรมและเทคโนโลยี](#2-สถาปัตยกรรมและเทคโนโลยี)
3. [โครงสร้างไดเรกทอรี](#3-โครงสร้างไดเรกทอรี)
4. [โครงสร้างฐานข้อมูล](#4-โครงสร้างฐานข้อมูล)
5. [การติดตั้งระบบจากศูนย์](#5-การติดตั้งระบบจากศูนย์)
6. [การปรับปรุง (Patches)](#6-การปรับปรุง-patches)
7. [การตั้งค่า Email (Gmail)](#7-การตั้งค่า-email-gmail)
8. [การรันระบบ](#8-การรันระบบ)
9. [การแก้ปัญหา (Troubleshooting)](#9-การแก้ปัญหา-troubleshooting)
10. [บัญชีผู้ใช้และสิทธิ์](#10-บัญชีผู้ใช้และสิทธิ์)

---

## 1. ภาพรวมระบบ

**Sahana Eden** (Emergency Development Environment) เป็นแพลตฟอร์มโอเพนซอร์สสำหรับสร้างแอปพลิเคชันเว็บเพื่อจัดการเหตุฉุกเฉินและภัยพิบัติ พัฒนาโดย Sahana Software Foundation ใช้เฟรมเวิร์ก **web2py** ภาษา Python

จุดประสงค์หลักของระบบ:
- ประสานงานระหว่างหน่วยงานรัฐ องค์กร NGOs และประชาชนในช่วงภัยพิบัติ
- ลงทะเบียนผู้ประสบภัย / คนหาย (DVI/DVR)
- จัดการอาสาสมัครและบุคลากร (HRM)
- จัดการสินค้าคงคลังและคลังสินค้า (Inventory)
- จัดการศูนย์พักพิง (Shelter / CR)
- แสดงแผนที่และข้อมูลเชิงพื้นที่ (GIS)
- ส่งการแจ้งเตือนภัย (CAP)
- ส่งข้อความ/SMS/Email (Messaging)

แพ็คเกจนี้ประกอบด้วย:
- ไฟล์ที่ปรับปรุงแล้ว 5 ไฟล์ (patches)
- สคริปต์ช่วยเหลือ 3 ไฟล์
- snapshot ฐานข้อมูล SQLite (พร้อมข้อมูล demo)
- schema dump (Markdown + JSON)
- ภาพหน้าจอระบบ 6 ภาพ

---

## 2. สถาปัตยกรรมและเทคโนโลยี

### 2.1 Stack เทคโนโลยี

| ชั้น | เทคโนโลยี | เวอร์ชั่น |
|------|-----------|----------|
| เฟรมเวิร์กหลัก | web2py | 3.3.3-stable (commit 9005306) |
| ภาษา | Python | 3.11+ (ทดสอบบน 3.12) |
| ORM | PyDAL | (submodule ของ web2py) |
| เทมเพลต | YATL | (built-in ของ web2py) |
| ฐานข้อมูล | SQLite | (default) — รองรับ PostgreSQL/MySQL ด้วย |
| เว็บเซิร์ฟเวอร์ | Rocket3 | (built-in HTTP server ของ web2py) |
| Reverse Proxy | Caddy | (สำหรับ HTTPS termination) |
| ฟรอนต์เอนด์ | jQuery, Foundation 5, OpenLayers, ExtJS, DataTables, D3.js |

### 2.2 สถาปัตยกรรมการ deploy (สภาพแวดล้อม sandbox)

```
┌─────────────────┐    HTTPS    ┌─────────────────┐    HTTP    ┌─────────────────┐
│                 │ ─────────→ │                 │ ────────→ │                 │
│   Web Browser   │            │   Caddy (port   │           │  web2py Rocket  │
│   (user)        │ ←───────── │   81, TLS)      │ ←──────── │  (port 3000)    │
│                 │            │                 │           │                 │
└─────────────────┘            └─────────────────┘           └─────────────────┘
                                                                     │
                                                                     │ SQLite
                                                                     ▼
                                                            ┌─────────────────┐
                                                            │  storage.db     │
                                                            │  (file-based)   │
                                                            └─────────────────┘
```

- **Caddy** ทำหน้าที่ terminate TLS (HTTPS) และ reverse proxy ไปยัง port 3000
- **web2py** รันเป็น daemon (double-fork) บน port 3000 ที่ `0.0.0.0`
- **SQLite** เก็บไฟล์ที่ `applications/eden/databases/storage.db`
- ภายนอกเข้าผ่าน URL: `https://preview-chat-<chat_id>.space-z.ai/eden/...`

### 2.3 โมดูลหลักของ Eden

| โมดูล | Controller | ฟังก์ชัน |
|-------|------------|---------|
| **gis** | gis.py | ระบบสารสนเทศภูมิศาสตร์ แผนที่ ตำแหน่ง |
| **org** | org.py | องค์กร / สำนักงาน / สาขา / sector |
| **hrm** | hrm.py | ทรัพยากรบุคคล / อาสาสมัคร / skill |
| **inv** | inv.py | คลังสินค้า / สินค้าคงคลัง / การเบิกจ่าย |
| **req** | req.py | คำขอ / การจัดหา |
| **project** | project.py | โครงการ / กิจกรรม / ผู้รับประโยชน์ |
| **cms** | cms.py | ระบบเนื้อหา / ข่าว / ประกาศ |
| **cap** | cap.py | การแจ้งเตือนภัย (Common Alerting Protocol) |
| **dvr** | dvr.py | ทะเบียนผู้ประสบภัย |
| **dvi** | dvi.py | สืบค้นคนหาย (Disaster Victim Identification) |
| **msg** | msg.py | SMS / Email / Twitter / การแจ้งเตือน |
| **asset** | asset.py | ครุภัณฑ์ / ทรัพย์สิน |
| **vehicle** | vehicle.py | ยานพาหนะ |
| **budget** | budget.py | งบประมาณ / kit / bundle |
| **deploy** | deploy.py | การประจำการ / การส่งกำลัง |
| **med** / **patient** / **hms** | *.py | การแพทย์ / ผู้ป่วย / โรงพยาบาล |
| **fire** | fire.py | สถานีดับเพลิง |
| **water** | water.py | ทรัพยากรน้ำ |
| **security** | security.py | รักษาความปลอดภัย |
| **cr** | cr.py | ศูนย์พักพิง (Shelter) |
| **sync** | sync.py | การซิงค์ข้อมูลระหว่าง instances |
| **admin** | admin.py | การดูแลระบบ / roles / translation |
| **default** | default.py | หน้าแรก / login / register / user |

---

## 3. โครงสร้างไดเรกทอรี

### 3.1 โครงสร้างระดับบน

```
/home/z/my-project/
├── eden-repo/                    ← Sahana Eden source code
│   ├── models/                   ← data models + config (Python)
│   ├── controllers/              ← request handlers (Python)
│   ├── views/                    ← HTML templates (YATL)
│   ├── modules/                  ← S3 framework modules
│   │   ├── core/                 ← core: aaa (auth), s3db, crud, etc.
│   │   ├── templates/            ← deployment templates (default, RLP, ...)
│   │   └── s3/                   ← S3 utilities
│   ├── static/                   ← JS, CSS, images, fonts
│   │   ├── scripts/              ← jQuery, OpenLayers, Foundation, etc.
│   │   ├── styles/               ← UI themes
│   │   └── themes/default/       ← default theme
│   ├── languages/                ← i18n files (incl. th.py for Thai)
│   ├── databases/                ← SQLite DB (auto-created)
│   ├── errors/                   ← error tickets (auto-created)
│   ├── sessions/                 ← session files (auto-created)
│   ├── uploads/                  ← user-uploaded files
│   ├── modules/templates/000_config.py  ← config template
│   └── ...
├── web2py/                       ← web2py framework
│   ├── gluon/                    ← core framework source
│   │   ├── tools.py              ← Mailer, Auth, Crud utilities
│   │   ├── main.py               ← WSGI entry point
│   │   ├── dal.py                ← Database Abstraction Layer
│   │   └── ...
│   ├── applications/
│   │   ├── eden → symlink to /home/z/my-project/eden-repo
│   │   ├── welcome/              ← default web2py welcome app
│   │   └── admin/                ← web2py admin interface
│   ├── routes.py                 ← URL routing (eden = default app)
│   └── web2py.py                 ← server launcher
├── scripts/                      ← helper scripts (in this bundle)
├── eden-logs/                    ← server logs + PID file
└── download/                     ← deliverables
```

### 3.2 โครงสร้างไฟล์ใน `models/`

web2py รันไฟล์ใน `models/` ตามลำดับตัวอักษร:

| ไฟล์ | หน้าที่ |
|------|--------|
| `000_config.py` | config หลัก (machine-specific) — ตั้ง public_url, mail, debug |
| `000_1st_run.py` | ตรวจสอบ first-run (สร้าง DB ถ้ายังไม่มี) |
| `00_db.py` | เปิดการเชื่อมต่อ database |
| `00_settings.py` | deployment settings (language, session, mailer setup) |
| `00_tables.py` | define table schema (via PyDAL) |
| `00_utils.py` | utility functions |
| `tasks.py` | scheduler task definitions |
| `zz_last.py` | hooks ที่รันท้ายสุด |
| `zzz_1st_run.py` | post-first-run tasks |

### 3.3 โครงสร้าง `modules/templates/`

Eden ใช้ระบบ "templates" เพื่อปรับแต่ง deployment:

| Template | สำหรับ |
|----------|--------|
| `default/` | default Sahana Eden deployment (ใช้ในแพ็คเกจนี้) |
| `RLP/` | Relief & Logistics (RED) |
| `RLPPTM/` | Risk & Loss Portfolio |
| `BETRA/` | Belize disaster management |
| `DIRECT/` | DRKCM (German Red Cross) |
| `DRKCM/` | DRKCM customization |
| `Disease/` | Disease surveillance |
| `GIMS/` | Geo-spatial Information Management |
| `MRCMS/` | Malaysian Red Crescent |
| `SAFIRE/` | Fire management |
| `skeleton/` | empty template (starting point) |

---

## 4. โครงสร้างฐานข้อมูล

### 4.1 ภาพรวม

- **Engine:** SQLite (file-based) → `applications/eden/databases/storage.db`
- **จำนวนตาราง:** 386 (ใน default template)
- **จำนวน records:** 1,216 rows (ข้อมูล demo + ผู้ใช้จริง)

> ดู schema dump แบบเต็มได้ที่ `database/schema.md` (10,820 บรรทัด) หรือ `database/schema.json`

### 4.2 ตารางหลัก (จัดตามกลุ่ม)

#### การยืนยันตัวตน (Authentication)
| ตาราง | Rows | หน้าที่ |
|-------|------|--------|
| `auth_user` | 5 | ผู้ใช้ (email, password hash, first_name, last_name, language, organisation_id) |
| `auth_group` | 9 | บทบาท (ADMIN, AUTHENTICATED, ANONYMOUS, EDITOR, MAP_ADMIN, ORG_ADMIN, ORG_GROUP_ADMIN) |
| `auth_membership` | 5 | การผูก user → group |
| `auth_event` | 22 | audit log (login, logout, register, etc.) |
| `auth_permission` | - | สิทธิ์ตาม table/record |

#### องค์กร (Organization)
| ตาราง | Rows | หน้าที่ |
|-------|------|--------|
| `org_organisation` | - | ข้อมูลองค์กร |
| `org_organisation_type` | 10 | ประเภทองค์กร |
| `org_organisation_organisation_type` | - | many-to-many |
| `org_organisation_user` | - | ผูกองค์กร ↔ user |
| `org_sector` | 11 | สาขาภาคธุรกิจ |
| `org_office_type` | 4 | ประเภทสำนักงาน |
| `org_site` | - | site / สาขา |

#### ระบบบุคคล (Person Registry)
| ตาราง | Rows | หน้าที่ |
|-------|------|--------|
| `pr_pentity` | - | base entity table (ทุก person/org/site สืบทอดจากนี้) |
| `pr_person` | - | ข้อมูลบุคคล |
| `pr_person_user` | - | ผูก pr_person ↔ auth_user |
| `pr_role` | - | บทบาทเฉพาะบุคคล |
| `pr_affiliation` | - | สังกัด |

#### ฝ่ายบุคคล (HRM)
| ตาราง | Rows | หน้าที่ |
|-------|------|--------|
| `hrm_human_resource` | - | บุคลากรในองค์กร |
| `hrm_skill` | 10 | ทักษะ |
| `hrm_certificate` | 20 | ใบรับรอง |
| `hrm_training` | - | การอบรม |

#### สินค้าคงคลัง (Inventory)
| ตาราง | หน้าที่ |
|-------|--------|
| `inv_warehouse` | คลังสินค้า |
| `inv_inv_item` | รายการสินค้าคงคลัง |
| `inv_inv_track` | การติดตาม movement |
| `inv_supplier` | ผู้จัดจำหน่าย |

#### โครงการ (Project)
| ตาราง | Rows | หน้าที่ |
|-------|------|--------|
| `project_project` | - | โครงการ |
| `project_activity_type` | 30 | ประเภทกิจกรรม |
| `project_theme` | 29 | หัวข้อโครงการ |
| `project_hazard` | 16 | อันตรายที่เกี่ยวข้อง |
| `project_beneficiary_type` | 10 | ประเภทผู้รับประโยชน์ |
| `project_status` | - | สถานะโครงการ |

#### ระบบแผนที่ (GIS)
| ตาราง | Rows | หน้าที่ |
|-------|------|--------|
| `gis_location` | 248 | ตำแหน่ง (lat/lon, admin levels) |
| `gis_location_tag` | 248 | tag ตำแหน่ง |
| `gis_hierarchy` | 97 | ลำดับชั้นที่ตั้ง (country → province → district → ...) |
| `gis_layer_config` | 78 | config ของแต่ละ layer |
| `gis_layer_entity` | 78 | binding layer ↔ entity |
| `gis_marker` | 77 | ตัว marker บนแผนที่ |
| `gis_style` | 24 | สไตล์ของ feature |
| `gis_layer_feature` | 19 | layer แบบ feature ( GeoJSON) |
| `gis_layer_tms` | 14 | TMS layer |
| `gis_layer_wms` | 14 | WMS layer |
| `gis_layer_openstreetmap` | 11 | OSM basemap |
| `gis_layer_google` | 7 | Google basemap |
| `gis_layer_bing` | - | Bing basemap |
| `gis_projection` | - | projection defs |

#### เนื้อหา (CMS)
| ตาราง | Rows | หน้าที่ |
|-------|------|--------|
| `cms_post` | 3 | โพสต์ / ข่าว / ประกาศ |
| `cms_post_module` | 3 | binding โพสต์ ↔ module |
| `cms_series` | - | หมวดโพสต์ (e.g. "Announcements") |
| `cms_status` | - | สถานะโพสต์ |
| `cms_tag` | - | tag |
| `cms_comment` | - | ความคิดเห็น |

#### การส่งข้อความ (Messaging)
| ตาราง | หน้าที่ |
|-------|--------|
| `msg_channel` | ช่องทาง (SMS modem, email, Twitter, ...) |
| `msg_log` | ประวัติการส่ง |
| `msg_outbox` | outbox |
| `msg_group` | group contact |
| `msg_contact` | ผู้รับ |

#### การแจ้งเตือนภัย (CAP)
| ตาราง | หน้าที่ |
|-------|--------|
| `cap_alert` | การแจ้งเตือน |
| `cap_info` | ข้อมูลการแจ้งเตือน (multi-language) |
| `cap_area` | พื้นที่เตือน |
| `cap_event` | เหตุการณ์ที่เตือน |

#### ทะเบียนผู้ประสบภัย (DVR)
| ตาราง | หน้าที่ |
|-------|--------|
| `dvr_case` | เคส |
| `dvr_case_event` | เหตุการณ์ในเคส |

#### การซิงค์และระบบ (Sync/Scheduler/S3)
| ตาราง | Rows | หน้าที่ |
|-------|------|--------|
| `s3_permission` | 55 | สิทธิ์ ACL (controller/function/tablename/record) |
| `scheduler_task` | - | งาน background |
| `scheduler_run` | - | ประวัติการรัน |
| `scheduler_worker` | - | worker ที่กำลังทำงาน |
| `scheduler_task_deps` | - | dependency ระหว่าง task |
| `sync_repository` | - | sync config |
| `sync_log` | - | sync log |

### 4.3 คอลัมน์สำคัญที่ใช้ในทุกตาราง (S3 base fields)

Eden's base table mixin ใส่คอลัมน์เหล่านี้ในทุกตารางโดยอัตโนมัติ:

| คอลัมน์ | Type | หน้าที่ |
|--------|------|--------|
| `id` | integer PK autoincrement | primary key |
| `uuid` | varchar(128) | UUID สำหรับ sync ระหว่าง instances |
| `mci` | integer | Master CI (sync metadata) |
| `deleted` | boolean ('T'/'F') | soft delete |
| `deleted_fk` | varchar(128) | deleted foreign key |
| `deleted_rb` | boolean | rule-based delete |
| `created_on` | datetime | เวลาสร้าง |
| `modified_on` | datetime | เวลาแก้ไขล่าสุด |

### 4.4 ตัวอย่าง schema: `auth_user`

```sql
CREATE TABLE auth_user (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  first_name VARCHAR(128),
  last_name VARCHAR(128),
  email VARCHAR(512),
  password VARCHAR(512),
  username VARCHAR(128),
  language VARCHAR(20),
  organisation_id INTEGER,
  org_group_id INTEGER,
  site_id INTEGER,
  link_user_to VARCHAR(128),
  registration_key VARCHAR(128),
  reset_password_key VARCHAR(128),
  locked BOOLEAN,
  failed_attempts INTEGER,
  locked_until DATETIME,
  deleted BOOLEAN,
  timestmp DATETIME,
  comments TEXT,
  uuid VARCHAR(128),
  created_on DATETIME,
  modified_on DATETIME
);

CREATE UNIQUE INDEX auth_user_email ON auth_user(email);
CREATE INDEX auth_user_uuid ON auth_user(uuid);
```

### 4.5 ผู้ใช้ในระบบ (5 accounts)

| id | email | ชื่อ | role | สถานะ | สร้างเมื่อ |
|----|-------|-----|------|-------|----------|
| 1 | `admin@example.com` | Admin User | ADMIN | ACTIVE | 2026-11-16 12:46:52 |
| 2 | `normaluser@example.com` | Normal User | AUTHENTICATED | ACTIVE | 2026-11-16 12:46:52 |
| 3 | `sungkom.pm@gmail.com` | Sungkom | AUTHENTICATED | ACTIVE | 2026-11-16 13:56:51 |
| 4 | `testuser-gsze61@example.com` | Test User | AUTHENTICATED | PENDING email verification | 2026-11-16 14:31:38 |
| 5 | `thai-test-3koheg@example.com` | ทดสอบ ระบบ | AUTHENTICATED | PENDING email verification | 2026-11-18 03:14:43 |

---

## 5. การติดตั้งระบบจากศูนย์

### 5.1 ข้อกำหนดเบื้องต้น (Prerequisites)

- **Python 3.11+** (ทดสอบบน 3.12)
- **git**
- ระบบปฏิบัติการ Linux (แนะนำ Debian/Ubuntu) หรือใช้ Docker

### 5.2 ติดตั้ง Python dependencies

```bash
# บน Debian/Ubuntu:
sudo apt install python3-lxml python3-dateutil python3-pyparsing
sudo apt install python3-shapely python3-geopy
sudo apt install python3-xlrd python3-xlwt python3-openpyxl
sudo apt install python3-reportlab

# หรือใช้ pip:
pip install --break-system-packages \
    lxml python-dateutil pyparsing requests \
    xlrd xlwt openpyxl reportlab shapely geopy qrcode \
    docx-mailmerge psycopg2-binary
```

### 5.3 Clone repositories

```bash
# Clone web2py framework
git clone https://github.com/web2py/web2py.git ~/web2py
cd ~/web2py
git reset --hard 9005306
git submodule update --init --recursive   # pulls pydal, rocket3, yatl
cd ~

# Clone Sahana Eden
git clone https://github.com/skpuan07-cmd/eden.git ~/eden
# หรือใช้ upstream: git clone https://github.com/sahana/eden.git ~/eden
```

### 5.4 ลิงก์ Eden เข้ากับ web2py

```bash
cd ~/web2py/applications
ln -s ~/eden eden
cd ~
```

### 5.5 สร้าง config จาก template

```bash
cd ~/eden
cp modules/templates/000_config.py models/000_config.py
```

แก้ไข `models/000_config.py`:
```python
# ตั้งเป็น True เมื่อแก้ไข config เสร็จ
FINISHED_EDITING_CONFIG_FILE = True

# (ถ้า dev) เปิด debug mode
settings.base.debug = True

# ตั้ง public URL ของ instance
settings.base.public_url = "https://preview-chat-<chat_id>.space-z.ai"

# (ถ้าใช้ Gmail ส่งเมล)
settings.mail.server = "smtp.gmail.com:587"
settings.mail.tls = True
settings.mail.login = "sungkom.pm@gmail.com:YOUR_APP_PASSWORD"
settings.mail.sender = "'Sahana Eden' <sungkom.pm@gmail.com>"
```

### 5.6 First-run setup (สร้าง DB + populate ข้อมูล demo)

```bash
cd ~/web2py
python web2py.py -S eden -M -R applications/eden/static/scripts/tools/noop.py
```

ผลที่ควรเห็น:
```
*** FIRST RUN - SETTING UP DATABASE ***
Setting Up System Roles...
Setting Up Scheduler Tasks...
Creating Database Tables (this can take a minute)...
Database Tables Created. (0.53 sec)
Importing default/base...
Imports for default/base complete (0.76 sec)
...
*** FIRST RUN COMPLETE ***
```

คำเตือนที่ "ปกติ" (optional dependencies):
- `GIS unresolved dependency: GDAL required for Shapefile support`
- `S3Msg unresolved dependency: pyserial required for Serial port modem usage`
- `S3MSG unresolved dependency: sgmllib3k required for Feed import on Python 3.x`
- `GIS unresolved dependency: selenium required for Map printing support`

### 5.7 วางไฟล์ที่ปรับปรุงแล้ว (Patches)

```bash
# สมมติแตกแพ็คเกจนี้ไว้ที่ ~/eden-bundle/
cp ~/eden-bundle/modified_files/eden_models_000_config.py      ~/eden/models/000_config.py
cp ~/eden-bundle/modified_files/eden_models_00_settings.py     ~/eden/models/00_settings.py
cp ~/eden-bundle/modified_files/eden_modules_core_aaa_auth.py  ~/eden/modules/core/aaa/auth.py
cp ~/eden-bundle/modified_files/web2py_gluon_tools.py          ~/web2py/gluon/tools.py
cp ~/eden-bundle/modified_files/web2py_routes.py               ~/web2py/routes.py
```

### 5.8 (Optional) ใช้ DB snapshot ที่เตรียมไว้

```bash
cp ~/eden-bundle/database/storage.db ~/eden/databases/storage.db
```

### 5.9 ตั้ง routes.py (ตั้ง eden เป็น default app)

```bash
cat > ~/web2py/routes.py <<'EOF'
routers = dict(
    BASE=dict(
        default_application='eden',
        default_controller='default',
        default_function='index',
    )
)
EOF
```

### 5.10 สตาร์ทเซิร์ฟเวอร์

```bash
bash ~/eden-bundle/scripts/start_eden.sh
# หรือ:
python3 ~/eden-bundle/scripts/launch_eden_daemon.py

# เปิดเบราว์เซอร์:
# http://127.0.0.1:3000/eden
```

---

## 6. การปรับปรุง (Patches)

### 6.1 Patch: `gluon/tools.py` (Python 3 mailer bug fix)

**ปัญหา:** web2py 3.3.3 มี legacy Python 2 code ใน `Mail.send()`:
```python
text = text.read().decode("utf8")
```
ใน Python 3, `file.read()` คืน `str` อยู่แล้ว (ไม่ใช่ bytes) → เรียก `.decode()` บน str → `AttributeError`

**อาการ:** register user ใหม่ → "internal error" เพราะ Eden เรียก `mailer.send()` ที่มี bug

**แก้ไข:** บรรทัด 549-552 ของ `gluon/tools.py`:
```python
# เดิม:
if not isinstance(text, str):
    text = text.read().decode("utf8")

# ใหม่:
if not isinstance(text, str):
    raw_text = text.read()
    if isinstance(raw_text, bytes):
        text = raw_text.decode("utf8")
    else:
        text = raw_text
```

(ใช้กับทั้ง `text` และ `html` parameter)

### 6.2 Patch: `modules/core/aaa/auth.py` (str() coercion for mailer messages)

**ปัญหา:** `messages.verify_email_subject` เป็น web2py lazy `T()` object → `% system` คืน lazy object ไม่ใช่ str → ส่งให้ mailer แล้ว trigger bug ใน `gluon/tools.py`

**แก้ไข:** ครอบด้วย `str()` รอบ subject/message ก่อนส่งให้ mailer (match upstream `nursix-dev` branch):
```python
# บรรทัด 1633-1634 (verify_email flow):
subject = str(messages.verify_email_subject % system),
message = str(messages.verify_email % system),

# บรรทัด 1695-1696 (reset_password flow):
subject = str(self.messages.reset_password_subject),
message = str(message)):
```

### 6.3 Patch: `models/00_settings.py` (HTTPS session secure)

**เพิ่ม block:**
```python
# Use secure session cookie over HTTPs
if request.is_https:
    session.secure()
```

**เหตุผล:** เมื่อเข้าผ่าน HTTPS (ผ่าน Caddy proxy), session cookie ควรมี flag `Secure` เพื่อป้องกัน browser ส่ง cookie ผ่าน HTTP โดยไม่ตั้งใจ

### 6.4 Patch: `models/000_config.py` (config หลัก)

การตั้งค่าที่เปลี่ยนจาก template:
```python
FINISHED_EDITING_CONFIG_FILE = True           # (จาก False)
settings.base.debug = True                     # (จาก False) — เปิด debug สำหรับ dev
settings.base.public_url = "https://preview-chat-f56af4cf-fc19-4268-af2c-c9ae7d8ee99a.space-z.ai"
                                               # ( uncomment และตั้ง URL ภายนอกจริง)

# Email settings
settings.mail.server  = "smtp.gmail.com:587"
settings.mail.tls     = True
settings.mail.login   = "sungkom.pm@gmail.com:GMAIL_APP_PASSWORD_PLACEHOLDER"
settings.mail.sender  = "'Sahana Eden' <sungkom.pm@gmail.com>"
settings.mail.approver = "sungkom.pm@gmail.com"
settings.mail.limit   = 1000
```

### 6.5 Patch: `web2py/routes.py` (default app)

```python
routers = dict(
    BASE=dict(
        default_application='eden',      # เดิมคือ 'welcome'
        default_controller='default',
        default_function='index',
    )
)
```

**เหตุผล:** เมื่อ user เข้า `/` (root URL) ให้ redirect ไป `/eden/` โดยอัตโนมัติ ไม่ตกไปที่ default `welcome` app

### 6.6 Thai language support (already in upstream)

ตรวจพบว่าใน repo มี Thai language support อยู่แล้วใน `models/00_settings.py`:
```python
elif language == "th":
    s3.language = "th_TH"
```

และมี `languages/th.py` สำหรับ translation strings — ระบบรองรับภาษาไทยโดย default

---

## 7. การตั้งค่า Email (Gmail)

### 7.1 config ปัจจุบัน

```python
settings.mail.server  = "smtp.gmail.com:587"
settings.mail.tls     = True
settings.mail.login   = "sungkom.pm@gmail.com:GMAIL_APP_PASSWORD_PLACEHOLDER"
settings.mail.sender  = "'Sahana Eden' <sungkom.pm@gmail.com>"
settings.mail.approver = "sungkom.pm@gmail.com"   # คำขออนุมัติ user ใหม่ → ส่งมาที่นี่
settings.mail.limit   = 1000                       # ส่งได้สูงสุด 1000 ฉบับ/วัน
```

### 7.2 การขอ Gmail App Password (16 ตัว)

Gmail บังคับใช้ App Password ตั้งแต่ปี 2022 (ไม่ยอมรับ password ปกติสำหรับ SMTP)

**ขั้นตอน:**
1. เปิด **2-Step Verification** ที่ https://myaccount.google.com/security
2. สร้าง **App Password** ที่ https://myaccount.google.com/apppasswords
   - เลือก "Mail"
   - ตั้งชื่อ device อะไรก็ได้ (เช่น "eden-server")
   - กดสร้าง → ได้รหัส **16 ตัว** (เช่น `abcd efgh ijkl mnop`)
   - คัดลอกไว้ (เอาช่องว่างออก)

### 7.3 วิธีใส่ App Password

**วิธีที่ 1: ใช้สคริปต์ (แนะนำ)**
```bash
bash scripts/set_gmail_password.sh abcdefghijklmnop
# แทน abcdefghijklmnop ด้วย App Password 16 ตัวของคุณ
```

สคริปต์จะ:
- แทนที่ `GMAIL_APP_PASSWORD_PLACEHOLDER` ใน `models/000_config.py`
- restart web2py daemon ให้โหลดค่าใหม่
- ตรวจสอบว่าทุกอย่างพร้อมใช้

**วิธีที่ 2: แก้ไขไฟล์ตรงๆ**
```python
# ใน models/000_config.py
settings.mail.login = "sungkom.pm@gmail.com:YOUR_APP_PASSWORD_HERE"
```
แล้ว restart:
```bash
kill -TERM $(cat /home/z/my-project/eden-logs/web2py.pid)
python3 scripts/launch_eden_daemon.py
```

### 7.4 กรณีที่ยังไม่ใส่ App Password

ระบบจะยังทำงานได้ แต่:
- Register user ใหม่ → user ถูกสร้างใน DB แต่**ส่งอีเมลยืนยันตัวตนไม่ได้** → ขึ้นข้อความ:
  > "Unable to send verification email - either your email is invalid or our email server is down"
- User จะอยู่ในสถานะ `PENDING email verification` (regkey เริ่มด้วย `sha512$`)
- ไม่สามารถ login ได้จนกว่าจะ verify email (หรือ admin ลบ regkey ใน DB ด้วยมือ)

### 7.5 การปิดการยืนยันอีเมล (ถ้ายังไม่มี App Password)

ถ้าต้องการให้ register แล้วใช้งานได้ทันทีโดยไม่ต้องยืนยันอีเมล:

```python
# ใน models/000_config.py (เพิ่มบรรทัดเหล่านี้)
settings.auth.registration_requires_verification = False
settings.auth.registration_requires_approval = False
```

---

## 8. การรันระบบ

### 8.1 สคริปต์สตาร์ทเซิร์ฟเวอร์

`scripts/start_eden.sh`:
```bash
bash scripts/start_eden.sh
# default port 3000, ใช้ password "eden_admin_2026"
# หรือกำหนดเอง:
PORT=8080 PASS=mySecret bash scripts/start_eden.sh
```

สคริปต์จะ:
1. ตรวจสอบ port ว่าง
2. launch web2py เป็น **double-fork daemon** (PPID=1, อยู่รอดข้าม bash session)
3. รอ 30 วินาทีให้ port ฟัง
4. แสดง URL + credentials

### 8.2 launcher daemon (low-level)

`scripts/launch_eden_daemon.py` — ใช้ Python `os.fork()` สองครั้งตาม POSIX daemon pattern:
1. fork ครั้งที่ 1: parent exit ทันที, child ทำงานต่อ
2. `os.setsid()`: สร้าง session ใหม่ (detach จาก controlling terminal)
3. fork ครั้งที่ 2: ป้องกัน daemon reacquire TTY
4. redirect stdin/stdout/stderr ไป log file
5. write PID ไป `eden-logs/web2py.pid`
6. `os.execvp("python3", ["python3", "web2py.py", ...])` เริ่มทำงาน

ผลลัพธ์: process PPID=1 (init), อยู่รอดข้ามการ exit ของ bash ที่เรียก

### 8.3 การหยุดเซิร์ฟเวอร์

```bash
kill -TERM $(cat /home/z/my-project/eden-logs/web2py.pid)
# หรือ:
pkill -f "web2py.py"
```

### 8.4 การดู log

```bash
tail -f /home/z/my-project/eden-logs/web2py_3000.log
```

### 8.5 การดู error tickets

```bash
ls -lt /home/z/my-project/eden-repo/errors/ | head -10
```

ไฟล์ ticket ชื่อตามรูปแบบ: `<client_ip>.<date>.<time>.<uuid>`
เปิดอ่านด้วย web2py admin UI: `http://127.0.0.1:3000/admin/default/tickets/<ticket_id>`

---

## 9. การแก้ปัญหา (Troubleshooting)

### 9.1 "internal error" ตอน register user

**สาเหตุ:** bug ใน `gluon/tools.py:549` (legacy Python 2 `.decode()` บน str)

**แก้:** ติดตั้ง patch ใน `modified_files/web2py_gluon_tools.py` และ `modified_files/eden_modules_core_aaa_auth.py`

### 9.2 Login ไม่เข้า แม้กรอกข้อมูลถูกต้อง

**สาเหตุไปได้หลายอย่าง:**

1. **เข้าผิด app** — URL `/welcome/default/user/login` เป็นหน้า login ของ web2py welcome app (default) ไม่ใช่ Eden
   - **แก้:** ใช้ `/eden/default/user/login` หรือติดตั้ง `routes.py` ให้ `/` redirect ไป `/eden/`

2. **`public_url` ผิด** — ถ้าตั้งเป็น `http://127.0.0.1:8000` แต่ user เข้าผ่าน URL อื่น → absolute URLs ใน redirect จะ break
   - **แก้:** ตั้ง `public_url` ให้ตรง URL ที่ user ใช้เข้าจริง

3. **Caddy proxy ผิด port** — Caddy proxy ไปที่ port 3000 (default สำหรับ Next.js) ถ้า web2py รันบน port อื่น → external URL คืน 502
   - **แก้:** รัน web2py บน port 3000

4. **Cross-domain cookie issue** — ถ้า cookie ตั้ง domain เป็น `127.0.0.1` แต่ user เข้า URL อื่น → browser ไม่ส่ง cookie กลับ
   - **แก้:** ใช้ patch `00_settings.py` ที่เพิ่ม `if request.is_https: session.secure()` และอย่าตั้ง cookie domain ใน config

### 9.3 "Unable to send verification email"

**สาเหตุ:** `mail.login` ยังเป็น placeholder หรือ App Password ผิด

**แก้:**
- ตั้ง Gmail App Password ด้วย `scripts/set_gmail_password.sh`
- หรือปิด `settings.auth.registration_requires_verification = False`

### 9.4 Server ตายหลัง bash session จบ

**สาเหตุ:** ใช้ `setsid ... &` แต่กระบวนการยังถูก cleanup เมื่อ parent process exit

**แก้:** ใช้ `scripts/launch_eden_daemon.py` ที่ใช้ double-fork pattern (PPID=1 หลัง fork ครั้งที่สอง)

### 9.5 Database schema migration

ถ้าเปลี่ยน Eden version (เช่น จาก fork skpuan07-cmd ไป upstream nursix-dev) schema อาจต่างกัน:

```python
# ใน models/000_config.py
settings.base.migrate = True       # auto-migrate ตอน start
settings.base.fake_migrate = True  # สร้าง .table files ใหม่โดยไม่ alter schema (ใช้ตอน migrate จาก version เก่า)
```

### 9.6 ระบบช้าตอน first request

First request หลัง restart จะช้า (5-10 วินาที) เพราะ web2py compile Python code → `.pyc` ครั้งแรก คำขอถัดไปจะเร็วขึ้น

### 9.7 Optional dependencies ที่ยังไม่ได้ติดตั้ง

| Warning | การติดตั้ง | ใช้ตอนไหน |
|---------|----------|---------|
| `GDAL required for Shapefile support` | `pip install GDAL` (ยาก — ต้อง build from source หรือใช้ conda) | import Shapefile |
| `pyserial required for Serial port modem` | `pip install pyserial` | SMS modem |
| `sgmllib3k required for Feed import` | `pip install sgmllib3k` | RSS feed import |
| `selenium required for Map printing` | `pip install selenium` + driver | print map เป็น PDF |

---

## 10. บัญชีผู้ใช้และสิทธิ์

### 10.1 System Roles (auth_group)

| Role | ID | สิทธิ์ |
|------|-----|--------|
| `ADMIN` | 1 | ทุกอย่าง |
| `AUTHENTICATED` | 2 | ทุก user ที่ login แล้ว |
| `ANONYMOUS` | 3 | ผู้ใช้ที่ยังไม่ login (read public data) |
| `EDITOR` | (ถ้ามี) | แก้ไข content |
| `MAP_ADMIN` | 4 | จัดการ GIS layers |
| `ORG_ADMIN` | 5 | จัดการองค์กรของตัวเอง |
| `ORG_GROUP_ADMIN` | 6 | จัดการ org group |

### 10.2 ACL System (s3_permission)

การกำหนดสิทธิ์แบบละเอียดที่ระดับ `controller` / `function` / `tablename` / `record`:
- `oacl` — owned ACL (สิทธิ์สำหรับ record ที่ user "own")
- `uacl` — unowned ACL (สิทธิ์สำหรับ record อื่น)
- ค่าที่เป็นไปได้: `CREATE`, `READ`, `UPDATE`, `DELETE`, `LIST`, `SEARCH`, `REVIEW`, `EXPORT`, `IMPORT`, `ALLOCATE`, `MAP_ADMIN`, `ORG_ADMIN`

### 10.3 การสร้าง admin ใหม่

```python
# ใน web2py shell:
cd ~/web2py
python3 web2py.py -S eden -M
>>> from gluon import current
>>> db = current.db
>>> auth_user = db.auth_user
>>> user_id = auth_user.insert(
...     first_name="New",
...     last_name="Admin",
...     email="newadmin@example.com",
...     password=auth_user.password.validate("StrongPassword!")[0],
...     registration_key="",  # empty = active
... )
>>> db.auth_membership.insert(user_id=user_id, group_id=1)  # ADMIN group
>>> db.commit()
```

### 10.4 การ reset password โดยตรงใน DB

```python
>>> user = db(db.auth_user.email == "user@example.com").select().first()
>>> user.update_record(
...     password=db.auth_user.password.validate("NewPassword!")[0],
...     reset_password_key="",
...     registration_key="",
... )
>>> db.commit()
```

---

## ภาคผนวก: ลิงก์ที่เกี่ยวข้อง

- **GitHub Repository (fork):** https://github.com/skpuan07-cmd/eden
- **GitHub Repository (upstream):** https://github.com/sahana/eden
- **web2py Repository:** https://github.com/web2py/web2py
- **Documentation (ReadTheDocs):** https://eden-asp.readthedocs.io
- **Wiki:** https://eden.sahanafoundation.org
- **Mailing list:** https://groups.google.com/g/eden-asp

---

*เอกสารฉบับนี้จัดทำเมื่อ 2026-11-18 — สำหรับ Sahana Eden v6.2 บน web2py 3.3.3-stable (Python 3.12)*
