# รายงานการศึกษาและติดตั้งระบบ Sahana Eden

**Repository:** https://github.com/skpuan07-cmd/eden.git
**วันที่ติดตั้ง:** 2026-11-16
**สถานะ:** ติดตั้งสำเร็จ ระบบทำงานได้ปกติ

---

## 1. ระบบคืออะไร

**Sahana Eden** (Emergency Development Environment) เป็นแพลตฟอร์มโอเพนซอร์สสำหรับสร้างแอปพลิเคชัน
เว็บเพื่อจัดการเหตุฉุกเฉินและภัยพิบัติ พัฒนาบนเฟรมเวิร์ก **web2py** (ภาษา Python)

ฟังก์ชันหลักที่มีให้ในเทมเพลต `default` (ที่เราติดตั้ง):
- **gis** — ระบบสารสนเทศภูมิศาสตร์ / แผนที่
- **org** — จัดการองค์กร / สำนักงาน / สาขา
- **hrm** — จัดการทรัพยากรบุคคล / อาสาสมัคร
- **inv** — จัดการสินค้าคงคลัง / คลังสินค้า
- **req** — จัดการคำขอ / การจัดหา
- **cr** — จัดการศูนย์พักพิง
- **project** — จัดการโครงการ / กิจกรรม
- **cms** — ระบบเนื้อหา / ข่าวสาร
- **cap** — การแจ้งเตือนภัย (Common Alerting Protocol)
- **dvr** — ทะเบียนผู้ประสบภัย / คนหาย
- **msg** — ระบบส่งข้อความ (SMS / Email / Twitter)
- และอีกหลายโมดูล (asset, budget, deploy, fire, hms, med, patient, security, supply, transport, water …)

## 2. สถาปัตยกรรมและเทคโนโลยี

| ชั้น | เทคโนโลยี |
|------|-----------|
| เฟรมเวิร์กหลัก | web2py 3.3.3-stable (commit 9005306) |
| ภาษา | Python 3.12 |
| ORM | PyDAL (submodule ของ web2py) |
| เทมเพลต | YATL (ของ web2py) |
| ฐานข้อมูล (ค่าเริ่มต้น) | SQLite (เก็บใน `eden-repo/databases/`) |
| เว็บเซิร์ฟเวอร์ | Rocket (built-in ของ web2py) |
| ฟรอนต์เอนด์ | jQuery, Foundation, OpenLayers, ExtJS, DataTables, D3 |
| ไลบรารีเสริม | lxml, dateutil, pyparsing, requests, shapely, geopy, reportlab, openpyxl, xlrd, xlwt, qrcode |

> หมายเหตุ: หากต้องการใช้ PostgreSQL ในโปรดักชัน ให้แก้ `models/000_config.py` บรรทัด `settings.database.db_type = "postgres"`

## 3. โครงสร้างไดเรกทอรีที่ติดตั้ง

```
/home/z/my-project/
├── eden-repo/                    ← ซอร์สโค้ด Eden (clone จาก GitHub)
│   ├── models/000_config.py      ← ไฟล์ตั้งค่า (สร้างจาก template)
│   ├── databases/                ← SQLite database (สร้างตอน first run)
│   ├── modules/templates/        ← เทมเพลตการปรับใช้ (default, RLP, …)
│   ├── controllers/              ← controllers ของแต่ละโมดูล
│   ├── models/  views/  static/  ← โครงสร้างมาตรฐานของ web2py
│   └── ...
├── web2py/                       ← เฟรมเวิร์ก web2py (clone จาก GitHub)
│   ├── applications/eden         ← symlink -> /home/z/my-project/eden-repo
│   ├── gluon/                    ← แกนกลางของ web2py
│   └── ...
├── scripts/start_eden.sh         ← สคริปต์สตาร์ทเซิร์ฟเวอร์
├── eden-logs/                    ← log ของเซิร์ฟเวอร์
│   ├── web2py.log
│   └── web2py.pid
└── upload/                       ← ไฟล์ zip ต้นฉบับที่ผู้ใช้แนบมา
```

## 4. ขั้นตอนที่ทำการติดตั้ง (สรุป)

1. **Clone repository ของ Eden** จาก `https://github.com/skpuan07-cmd/eden.git`
2. **Clone web2py** จาก `https://github.com/web2py/web2py.git` และ `git reset --hard 9005306` รวมถึง `git submodule update --init --recursive` (ดึง pydal, rocket3, yatl)
3. **ติดตั้ง dependencies** ด้วย `pip install --break-system-packages`: lxml, python-dateutil, pyparsing, requests, xlrd, xlwt, openpyxl, reportlab, shapely, geopy, qrcode, docx-mailmerge, psycopg2-binary
4. **สร้าง symlink** `/home/z/my-project/web2py/applications/eden` -> `/home/z/my-project/eden-repo`
5. **สร้างไฟล์ config** คัดลอก `modules/templates/000_config.py` ไปยัง `models/000_config.py`
6. **แก้ไข config** ตั้ง `FINISHED_EDITING_CONFIG_FILE = True` และเปิด `settings.base.debug = True` (โหมดพัฒนา)
7. **First-run database setup** รันคำสั่ง:
   ```
   cd /home/z/my-project/web2py
   python3 web2py.py -S eden -M -R applications/eden/static/scripts/tools/noop.py
   ```
   ผลลัพธ์: สร้างตารางทั้งหมด (0.53 วินาที) นำเข้าข้อมูลตั้งต้น (1.64 วินาที) สร้างดัชนี
   ข้อความสำคัญ: `*** FIRST RUN COMPLETE ***`
8. **ทดสอบสตาร์ทเซิร์ฟเวอร์** และตรวจสอบ HTTP endpoints

## 5. ผลการทดสอบระบบ

| Endpoint | HTTP | ขนาด | เวลาตอบ | หมายเหตุ |
|----------|------|------|--------|--------|
| `GET /eden/default/index` | 200 | 42,763 B | ~2.0 s | หน้า Login ของ Eden |
| `GET /eden/default/user/login` | 200 | 40,012 B | ~0.06 s | ฟอร์มล็อกอินมี field `email` + `password` |
| `GET /eden/static/themes/default/foundation/app.css` | 200 | 118,333 B | <1 ms | CSS โหลดได้ปกติ |

หัวข้อสำคัญ: `<title>Login</title>`, คำว่า "Sahana" พบ 4 ครั้ง, "Eden" พบ 137 ครั้งในหน้าแรก →
ยืนยันว่าระบบ Eden ทำงานได้จริง ไม่ใช่หน้า error หรือหน้าว่าง

## 6. บัญชีผู้ใช้ตัวอย่าง (สร้างโดย first run)

| Email | รหัสผ่าน | บทบาท |
|-------|---------|-------|
| `admin@example.com` | `testing` | ผู้ดูแลระบบ (Administrator) |
| `normaluser@example.com` | `testing` | ผู้ใช้ทั่วไป |

## 7. วิธีสตาร์ท/หยุดเซิร์ฟเวอร์

**สตาร์ท:**
```bash
bash /home/z/my-project/scripts/start_eden.sh
# หรือกำหนดพอร์ต/รหัสผ่านเอง:
PORT=8080 PASS=mySecret bash /home/z/my-project/scripts/start_eden.sh
```

**เข้าใช้งาน:**
- แอป Eden: http://127.0.0.1:8000/eden
- web2py admin: http://127.0.0.1:8000/admin (รหัสผ่านตามที่กำหนดในสคริปต์)

**ดู log:**
```bash
tail -f /home/z/my-project/eden-logs/web2py.log
```

**หยุด:**
```bash
kill -TERM $(cat /home/z/my-project/eden-logs/web2py.pid)
```

## 8. ข้อควรทราบและคำเตือนที่พบ (ไม่มีผลกระทบต่อการใช้งาน)

ระหว่าง first run มี WARNING เกี่ยวกับ optional dependencies ที่ไม่ได้ติดตั้ง:
- `GIS unresolved dependency: GDAL required for Shapefile support`
- `S3Msg unresolved dependency: pyserial required for Serial port modem usage`
- `S3MSG unresolved dependency: sgmllib3k required for Feed import on Python 3.x`
- `GIS unresolved dependency: selenium required for Map printing support`

สิ่งเหล่านี้เป็น dependency เสริมสำหรับฟังก์ชันเฉพาะทาง (Shapefile, SMS modem, RSS feed, map print)
หากต้องการใช้ฟังก์ชันเหล่านั้น สามารถติดตั้งเพิ่มภายหลังได้ด้วย
`pip install --break-system-packages GDAL pyserial sgmllib3k selenium`

นอกจากนี้ระบบแจ้ง S3LOG WARNING 2 ข้อที่ไม่มีผลกระทบ:
- `Ambiguous link/component alias (asset_asset.human_resource)`
- `Ambiguous link/component alias (req_req.job)`
- `Ambiguous link/component alias (sync_repository.job)`
