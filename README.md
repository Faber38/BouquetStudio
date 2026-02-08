# BouquetStudio

**BouquetStudio** ist ein lokaler Enigma2 Bouquet Editor (Python / PySide6),
der bewusst auf einen **expliziten Quelle-→-Ziel-Workflow** setzt.

Kein automatisches Umsortieren, keine versteckte Magie –  
nur das, was der Nutzer bewusst auswählt und speichert, wird übernommen.

---

## ✨ Aktueller Funktionsstand

### Projekt laden
- Öffnen eines Enigma2-Projektordners über  
  **Datei → Projekt öffnen…**
- Erwartete Struktur:
etc/enigma2/
├─ lamedb
├─ bouquets.tv
└─ userbouquet.*.tv


---

## 🧭 Bedienkonzept (wichtig)

### 1️⃣ Linke Spalte – Bouquets
- Anzeige aller Bouquets im Projekt
- Auswahl lädt das Bouquet

### 2️⃣ Mittlere Spalte – Quelle
- Zeigt **das komplette Bouquet**, wie es aktuell auf der Platte steht
- Dient **nur als Quelle**
- Drag erlaubt, Drop verboten
- Keine interne Sortierung relevant

### 3️⃣ Rechte Spalte – Ziel (Neue Reihenfolge)
- **Arbeitsbereich**
- Sender werden **explizit von der Quelle hierher gezogen**
- Reihenfolge wird hier per Drag&Drop festgelegt
- Nur diese Liste ist entscheidend beim Speichern

---

## 💾 Speichern (zentrales Prinzip)

Beim Klick auf **„Bouquet speichern“** gilt:

- **Ausschließlich der Inhalt der rechten Liste wird gespeichert**
- Das Bouquet wird **vollständig ersetzt**
- Keine automatisch angehängten Rest-Sender
- Ist die rechte Liste leer → kein Speichern

### Backup-Verhalten
- Vor jedem Speichern wird eine Sicherung angelegt:
userbouquet.xyz.tv.bak.YYYYMMDD-HHMMSS

- Die Originaldatei wird anschließend neu geschrieben

---

## 🔄 Laden / Neustart

- Beim Start oder Projektwechsel werden Bouquets **immer neu von der Platte geladen**
- Die mittlere Liste zeigt **den tatsächlichen Dateiinhalt**
- Die rechte Liste ist leer (bewusst – sie ist nur die „Baustelle“)

---

## 🛠️ Technischer Stand

- Python 3.10+
- PySide6 (Qt)
- Kein Cloud-Zwang, komplett lokal
- GitHub Actions CI:
- Syntax-/Compile-Check bei jedem Push
- Release-ZIP bei Versions-Tags (`v*`)

---

## 🏷️ Versionierung

- Semantic Versioning (`vMAJOR.MINOR.PATCH`)
- Releases werden automatisch bei Git-Tags erzeugt  
z. B.:
git tag v0.1.0
git push --tags


---

## 🚧 Geplant (Ausblick)

- Receiver-Anbindung (Download / Upload via SSH/SFTP)
- GUI-Reload / Enigma2 Restart
- Komfortfunktionen (Reload nach Speichern, Statusanzeigen)

---

## 📌 Leitgedanke

> Quelle = Referenz  
> Ziel = Entscheidung  
> Datei = Wahrheit
