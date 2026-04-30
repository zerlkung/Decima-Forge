# DecimaForge

> Decima Engine Archive Toolkit — extract, modify, and repack game archives from Horizon Zero Dawn / Death Stranding.

**⚠️ WORK IN PROGRESS — This project is under active development and not yet stable. APIs and CLI may change without notice. Test thoroughly before using on production data.**

---

## Features

- Parse and extract `.bin` archives (plain and encrypted)
- Decompress Oodle Kraken chunks (requires external DLL)
- Export/import localization text to JSON (21 languages)
- Extract font textures to DDS
- Resolve file paths from PrefetchList (hash → path lookup)
- Compute MurmurHash3_x64_128 path hashes
- Repack modified files into new archives

## Requirements

- **Python 3.10+**
- **Windows x64** (Oodle DLL is win64 only)
- **oo2core DLL** — Place `oo2core_7_win64.dll` (or other version) in the project directory, or set `DECIMA_GAME_DIR` environment variable.
  - *This DLL is part of RAD Game Tools' Oodle compression library. It is NOT included in this repository. You can obtain it from game installations that use Decima Engine.*

## Installation

```bash
git clone https://github.com/zerlkung/Decima-Forge.git
cd Decima-Forge
pip install -e .
```

Or run without installing:

```bash
cd Decima-Forge
python -m decimaforge <command>
```

## Quick Start

```bash
# List files in archive
decimaforge list initial.bin -a

# Extract file path list (use --prefetch for patch archives)
decimaforge file-list initial.bin
decimaforge file-list Patch_HZDTHAI.bin --prefetch initial.bin

# Unpack entire archive
decimaforge unpack initial.bin extracted/
decimaforge unpack Patch_HZDTHAI.bin --prefetch initial.bin

# Export Thai localization
decimaforge export-loc initial_english.bin --lang th
decimaforge export-loc Patch_HZDTHAI.bin --lang th --prefetch initial.bin

# Edit loc.json, then import back
decimaforge import-loc initial_english.bin loc.json --lang th

# Extract font textures
decimaforge extract-fonts initial.bin

# Compute path hash
decimaforge hash "ui/fonts/font_book.core"

# Repack modified files
decimaforge repack extracted/ new_archive.bin
```

## Commands

| Command | Usage | Description |
|---------|-------|-------------|
| `list` | `decimaforge list <archive> [-a]` | List files in archive (`-a` for all) |
| `extract` | `decimaforge extract <archive> <hash\|path> [output]` | Extract a single file |
| `unpack` | `decimaforge unpack <archive> [dir] [--prefetch] [--no-names]` | Unpack all files to directory |
| `repack` | `decimaforge repack <folder> [output]` | Repack folder (must have manifest.json) |
| `export-loc` | `decimaforge export-loc <archive> [output] [--lang] [--prefetch]` | Export localization to JSON |
| `import-loc` | `decimaforge import-loc <archive> <json> [dir] --lang` | Import localization from JSON |
| `extract-fonts` | `decimaforge extract-fonts <archive> [dir] [--prefetch]` | Extract font textures as DDS |
| `file-list` | `decimaforge file-list <archive> [output] [--prefetch]` | Extract prefetch file paths |
| `hash` | `decimaforge hash <path>` | Compute MurmurHash3 file path hash |

## Supported Languages

English, French, Spanish, German, Italian, Dutch, Portuguese, Chinese Traditional, Korean, Russian, Polish, Danish, Finnish, Norwegian, Swedish, Japanese, LATAM Spanish, LATAM Portuguese, Turkish, Arabic, Chinese Simplified (21 languages total)

## Architecture

```
decimaforge/
├── __init__.py      # Package metadata
├── __main__.py      # python -m decimaforge entry
├── cli.py           # CLI (argparse, 8 subcommands)
├── archive.py       # .bin archive read/write
├── core.py          # .core binary format parser
├── hash.py          # MurmurHash3_x64_128
├── compression.py   # Oodle Kraken (ctypes)
├── encryption.py    # XOR decryption
├── localization.py  # Text export/import
├── font.py          # Font texture → DDS
└── prefetch.py      # Hash → path mapping
```

## Credits

This project is built on research and reverse-engineering work from the community:

- **[Decima-Explorer](https://github.com/acrinym/Decima-Explorer)** — Archive structure, encryption algorithms, chunk layout (C++)
- **[decima-workshop](https://github.com/ShadelessFox/decima-workshop)** — Encryption salts, struct encryption/decryption, file table layout (Java)
- **[HZDCoreEditor](https://github.com/Nukem9/HZDCoreE)** — Core file format research, RTTI type system
- **[smhasher](https://github.com/aappleby/smhasher)** — MurmurHash3 reference implementation (public domain)

## License

This project is provided for educational and modding purposes. See individual source files for specific attribution. The Oodle compression library is proprietary software by RAD Game Tools and is not included.

---

# DecimaForge (ภาษาไทย)

> ชุดเครื่องมือสำหรับจัดการไฟล์เกม Decima Engine — Horizon Zero Dawn / Death Stranding

**⚠️ อยู่ระหว่างการพัฒนา — โปรเจคนี้ยังไม่เสถียร API และคำสั่งอาจเปลี่ยนแปลงโดยไม่แจ้งล่วงหน้า ควรทดสอบก่อนใช้กับข้อมูลจริง**

## ความสามารถ

- อ่านและแยกไฟล์ `.bin` archive (ทั้งแบบเข้ารหัสและไม่เข้ารหัส)
- แกะ/บีบอัดข้อมูล Oodle Kraken (ต้องใช้ DLL ภายนอก)
- ส่งออก/นำเข้าข้อความแปลภาษาเป็น JSON (21 ภาษา)
- ดึง texture ฟอนต์เป็นไฟล์ DDS
- ค้นหาชื่อไฟล์จาก PrefetchList (hash → path)
- คำนวณ MurmurHash3_x64_128
- แพ็คไฟล์กลับเป็น archive ใหม่

## ความต้องการ

- **Python 3.10+**
- **Windows x64** (Oodle DLL ใช้ได้เฉพาะ win64)
- **oo2core DLL** — วาง `oo2core_7_win64.dll` (หรือเวอร์ชันอื่น) ในโฟลเดอร์โปรเจค หรือตั้งค่า environment variable `DECIMA_GAME_DIR`
  - *DLL นี้เป็นส่วนหนึ่งของ Oodle compression library โดย RAD Game Tools ทางเราไม่ได้รวมมาให้ สามารถหาได้จากเกมที่ใช้ Decima Engine*

## ติดตั้ง

```bash
git clone https://github.com/zerlkung/Decima-Forge.git
cd Decima-Forge
pip install -e .
```

หรือรันโดยไม่ต้องติดตั้ง:

```bash
cd Decima-Forge
python -m decimaforge <command>
```

## วิธีใช้

```bash
# ดูไฟล์ใน archive
decimaforge list initial.bin -a

# ดึงรายชื่อไฟล์ (ใช้ --prefetch สำหรับ patch archive)
decimaforge file-list initial.bin
decimaforge file-list Patch_HZDTHAI.bin --prefetch initial.bin

# แกะ archive ทั้งหมด
decimaforge unpack initial.bin extracted/
decimaforge unpack Patch_HZDTHAI.bin --prefetch initial.bin

# ส่งออกข้อความภาษาไทย
decimaforge export-loc initial_english.bin --lang th
decimaforge export-loc Patch_HZDTHAI.bin --lang th --prefetch initial.bin

# แก้ไข loc.json แล้วนำเข้ากลับ
decimaforge import-loc initial_english.bin loc.json --lang th

# ดึงฟอนต์
decimaforge extract-fonts initial.bin

# คำนวณ hash
decimaforge hash "ui/fonts/font_book.core"

# แพ็คกลับ
decimaforge repack extracted/ new_archive.bin
```

## คำสั่ง

| คำสั่ง | วิธีใช้ | คำอธิบาย |
|---------|-------|-----------|
| `list` | `decimaforge list <archive> [-a]` | แสดงไฟล์ใน archive (`-a` แสดงทั้งหมด) |
| `extract` | `decimaforge extract <archive> <hash\|path> [output]` | แยกไฟล์เดี่ยว |
| `unpack` | `decimaforge unpack <archive> [dir] [--prefetch] [--no-names]` | แกะทุกไฟล์ไปโฟลเดอร์ |
| `repack` | `decimaforge repack <folder> [output]` | แพ็คโฟลเดอร์กลับ (ต้องมี manifest.json) |
| `export-loc` | `decimaforge export-loc <archive> [output] [--lang] [--prefetch]` | ส่งออกข้อความเป็น JSON |
| `import-loc` | `decimaforge import-loc <archive> <json> [dir] --lang` | นำเข้าข้อความจาก JSON |
| `extract-fonts` | `decimaforge extract-fonts <archive> [dir] [--prefetch]` | ดึงฟอนต์เป็น DDS |
| `file-list` | `decimaforge file-list <archive> [output] [--prefetch]` | ดึงรายชื่อไฟล์จาก prefetch |
| `hash` | `decimaforge hash <path>` | คำนวณ MurmurHash3 ของพาธ |

## ภาษาที่รองรับ

อังกฤษ, ฝรั่งเศส, สเปน, เยอรมัน, อิตาลี, ดัตช์, โปรตุเกส, จีนตัวเต็ม, เกาหลี, รัสเซีย, โปแลนด์, เดนมาร์ก, ฟินแลนด์, นอร์เวย์, สวีเดน, ญี่ปุ่น, สเปนลาตินอเมริกา, โปรตุเกสบราซิล, ตุรกี, อาหรับ, จีนตัวย่อ (21 ภาษา)

## เครดิต

โปรเจคนี้พัฒนาจากงานวิจัยและ reverse-engineering ของชุมชน:

- **[Decima-Explorer](https://github.com/acrinym/Decima-Explorer)** — โครงสร้าง archive, ขั้นตอนการเข้ารหัส, การจัดเรียง chunk (C++)
- **[decima-workshop](https://github.com/ShadelessFox/decima-workshop)** — Encryption salts, การเข้ารหัส/ถอดรหัส struct, ผัง file table (Java)
- **[HZDCoreEditor](https://github.com/Nukem9/HZDCoreE)** — งานวิจัย .core format, ระบบ RTTI type
- **[smhasher](https://github.com/aappleby/smhasher)** — MurmurHash3 reference implementation (public domain)

## ลิขสิทธิ์

โปรเจคนี้จัดทำเพื่อการศึกษาและการทำ mod เท่านั้น Oodle compression library เป็นซอฟต์แวร์ที่มีลิขสิทธิ์ของ RAD Game Tools และไม่ได้รวมอยู่ในโปรเจคนี้
