# BouquetStudio

**BouquetStudio** is a local Enigma2 bouquet editor (Python / PySide6)
built around a **strict source → target workflow**.

No automatic reordering, no hidden logic –  
**only what the user explicitly selects and saves is written.**

---

## ✨ Features

### Load project
- Open an Enigma2 project directory via **File → Open project…**
- Expected structure:
```
etc/enigma2/
├─ lamedb
├─ bouquets.tv
└─ userbouquet.*.tv
```

---

## 🧭 Workflow concept

### Left column – Bouquets
- Shows all available bouquets
- Selection defines the **target bouquet**
- Bouquets can be renamed or newly created
- Changes are only written on save

### Middle column – Source
- Displays the original bouquet file content
- Source only
- Drag allowed, drop disabled
- Search/filter applies only here

### Right column – Target
- Working area
- Services are explicitly dragged from source to target
- Order defined via drag & drop
- Only this list is saved

---

## 📌 Markers / Headers
- Markers are real Enigma2 markers (service type 64)
- 📌 is UI only
- Files are written in pure Enigma2 format

---

## 💾 Saving
- Only the right list is written
- Target bouquet is fully replaced
- Empty target → nothing is saved
- Automatic backups:
```
userbouquet.xyz.tv.bak.YYYYMMDD-HHMMSS
```

---

## 🛠️ Tech
- Python ≥ 3.10
- PySide6
- Fully local
- GitHub Actions CI (syntax & releases)

---

## 📌 Philosophy

> Source = reference  
> Target = decision  
> File = truth
