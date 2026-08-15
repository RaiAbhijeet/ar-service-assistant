<!--
  VORLAGE — jeden <PLATZHALTER> und jedes "TBD" ersetzen, sobald belegt.
  Keine Zahl eintragen, die nicht gemessen wurde. "TBD" ist ehrlich, eine falsche Zahl nicht.
  Muss im selben Commit wie README.md aktualisiert werden.
-->

# AR Service Assistant

**Mixed-Reality-Wartungsassistenz, die vollständig on-premise läuft.**
Man richtet eine Meta Quest 3S auf eine Anlage. Das System erkennt das Bauteil über die
Passthrough-Kamera, holt die passende Arbeitsanweisung aus dem Original-Servicehandbuch des
Herstellers und blendet die Schritte lagerichtig ein — gesprochen und geschrieben, auf
Deutsch. Keine Cloud. Kein Datenabfluss aus dem lokalen Netz.

🇬🇧 [English version](README.md)

![demo](docs/demo/demo.gif)

---

## Warum

Wartungstechniker in Luftfahrt, Schienenverkehr, Energie und Produktion arbeiten unter zwei
Randbedingungen gleichzeitig:

1. **Die Hände sind belegt und das Handbuch hat 400 Seiten.** Nachschlagen heißt, das Werkzeug
   abzulegen und die Arbeitsposition zu verlieren.
2. **Anlagendaten dürfen den Standort nicht verlassen.** Cloud-Assistenten sind damit keine
   Option — nicht aus Compliance-Gründen, über die man verhandeln könnte, sondern aus
   vertraglichen, über die man nicht verhandeln kann.

Bestehende AR-Wartungslösungen lösen (1) und ignorieren (2), oder sie lösen (2), indem sie auf
KI verzichten. Dieses Projekt löst beides: ein Vision-Language-Modell und eine
Retrieval-Pipeline auf einem einzelnen lokalen Rechner, das Headset als Thin Client.

---

## Ergebnisse

| Kennzahl | Zielwert | Gemessen |
|---|---|---|
| Retrieval Recall@5 (deutscher Golden Set, n=40) | ≥ 0,85 | TBD |
| Antworttreue (Judge + manuelle Prüfung) | ≥ 0,90 | TBD |
| Bauteilerkennung Top-1 (n=120, 3 Lichtsituationen) | ≥ 0,90 | TBD |
| **Rate falsch-sicherer Antworten** (falsches Bauteil bei Konfidenz > 0,8) | ≤ 0,02 | TBD |
| Time-to-First-Token (p95) | ≤ 1,5 s | TBD |
| Ende-zu-Ende bis zur ersten Sprachausgabe (p95) | ≤ 2,5 s | TBD |
| Frame-Time p95 bei 72 Hz | ≤ 13,9 ms | TBD |
| GC-Allokationen pro Frame im Dauerbetrieb | 0 B | TBD |
| Beginn des thermischen Throttlings | > 15 min | TBD |
| VRAM-Spitze | < 14 GB | TBD |
| **Ausgehende Bytes während eines vollständigen Demolaufs** | **0** | TBD |
| Kaltstart (`make up` → erste Antwort) | < 90 s | TBD |

Rohdaten und Diagramme: [`docs/benchmarks/`](docs/benchmarks/)

---

## Architektur

![Architektur](docs/architecture.png)

```
Meta Quest 3S  ──  Thin Client
  Passthrough Camera API ─► JPEG-Frame (640×480) ─┐
  Mikrofon ─► 16 kHz PCM ─────────────────────────┤  WebSocket / LAN
  Spatial Anchor + Schritt-Panel + Sprachausgabe ◄┘
                                │
Edge-Server (Dell Precision 7730 · Quadro P5200 16 GB · WSL2)
  FastAPI  →  FSM-Orchestrator
      ├─ whisper.cpp            Spracherkennung (de)
      ├─ Ollama / llama.cpp     Qwen3-VL, Q4_K_M — Bauteilerkennung + Antwortgenerierung
      ├─ Postgres + pgvector    Handbuch-Chunks, hybrides Retrieval (BM25 + dense)
      └─ Piper                  Sprachsynthese (de)
  Prometheus + Grafana          Durchsatz, Latenz, VRAM, GPU-Temperatur
  Docker-Netz ohne Default-Route
```

Details: [`docs/architecture.md`](docs/architecture.md)

---

## Engineering-Entscheidungen

Jede dieser Entscheidungen ist eine dokumentierte Abwägung, keine Voreinstellung:

| ADR | Entscheidung |
|---|---|
| [0001](docs/adr/0001-edge-inference-instead-of-on-device.md) | Inferenz auf einem Edge-Server statt im Headset — mit den Messungen, die das On-Device-Verfahren ausgeschlossen haben |
| [0002](docs/adr/0002-explicit-fsm-instead-of-agent-framework.md) | Expliziter endlicher Automat statt Agenten-Framework |
| [0003](docs/adr/0003-rag-instead-of-finetuning.md) | Retrieval über das echte Handbuch statt Fine-Tuning |
| [0004](docs/adr/0004-int4-quantization-no-fp16-on-pascal.md) | Ausschließlich Integer-Quantisierung — kein FP16-Pfad auf Pascal-Hardware |
| [0005](docs/adr/0005-openxr-instead-of-vendor-plugin.md) | OpenXR statt Vendor-XR-Plugin |
| [0006](docs/adr/0006-refusal-over-generation.md) | Die Antwortverweigerung ist ein gleichwertiges Ergebnis |

---

## Schnellstart

**Voraussetzungen:** Windows 11 mit WSL2 (oder Linux), NVIDIA-GPU mit Compute Capability ≥ 5.0
und Treiber ≥ 550, Docker, Unity 6 LTS mit Android Build Support, Meta Quest 3 / 3S im
Entwicklermodus.

```bash
git clone https://github.com/<USER>/ar-service-assistant
cd ar-service-assistant
cp .env.example .env          # ARSA_OBJECT und ARSA_HOST_IP setzen

make up                        # Edge-Stack starten
make ingest                    # Servicehandbuch laden, chunken, einbetten
make eval                      # Retrieval-Qualität prüfen, bevor man ihr vertraut

make apk && make install       # Build und Deployment auf das Headset
```

Das Servicehandbuch liegt **nicht** in diesem Repository. `make ingest` lädt es von der
öffentlichen Herstellerseite und prüft den in `objects/<object>/object.yaml` hinterlegten
SHA-256-Hash.

---

## Neues Objekt hinzufügen

Ohne Codeänderung:

```
objects/meine-anlage/
├── object.yaml            # Bauteilliste, Handbuch-URL + sha256, Konfidenzschwellen
└── reference/<part-id>/   # ca. 20 Referenzfotos je Bauteil
```

Danach `ARSA_OBJECT=meine-anlage make ingest`.

Enthaltene Objekte: `bike-drivetrain` (primär), `<zweites Objekt>` (belegt die
Konfigurierbarkeit).

---

## Hardware

Entwickelt und gemessen auf bewusst bescheidener Hardware, weil On-Premise-Inferenzrechner in
einer Werkshalle bescheiden sind:

| | |
|---|---|
| Edge-Server | Dell Precision 7730 — i7-8850H, 64 GB RAM, **NVIDIA Quadro P5200 16 GB (Pascal, CC 6.1)** |
| Headset | Meta Quest 3S (Snapdragon XR2 Gen 2, 8 GB) |
| Netz | LAN, 5-GHz-WLAN |

Pascal besitzt keine Tensor Cores und führt FP16 mit 1/64-Rate aus. Der gesamte Inferenzpfad
ist daher integer-quantisiert — siehe
[ADR-0004](docs/adr/0004-int4-quantization-no-fp16-on-pascal.md).

---

## On-Device-Inferenz: gemessen und verworfen

Das Sprachmodell direkt im Headset auszuführen wurde geprüft und verworfen. Die Referenzstudie
[LoXR (arXiv:2502.15761)](https://arxiv.org/abs/2502.15761) misst für eine Meta Quest 3
**5,77 Token/s** bei **9,7 % Akkuverlust in 10 Minuten** — der letzte Platz unter vier
getesteten XR-Geräten.

Dieses Repository erweitert die Messungen auf die **Quest 3S** und ergänzt die beiden
Kennzahlen, die LoXR nicht erhebt: **Time-to-First-Token** und **Frame-Time-Einfluss bei
gleichzeitig rendernder Szene**. Siehe
[`quest-llm-bench`](https://github.com/<USER>/quest-llm-bench) und
[`docs/benchmarks/on-device.md`](docs/benchmarks/on-device.md).

Edge-Inferenz ist zudem schlicht die richtige industrielle Architektur: Keine Anlage rechnet
auf dem Headset des Technikers, sondern auf einem Rechner in der Halle.

---

## Grenzen des Systems

- Die Erkennung arbeitet auf einer **geschlossenen Menge** der in `object.yaml` definierten
  Bauteile. Unbekannte Bauteile werden abgelehnt, nicht geraten.
- Erfordert eine LAN-Verbindung zum Edge-Server. Es gibt bewusst keinen On-Device-Fallback.
- Getestet ausschließlich bei Innenraumbeleuchtung zwischen <X> und <Y> Lux.
- Nur Deutsch. Englische Strings existieren, sind aber nicht gegen einen Golden Set geprüft.
- Die Anker-Stabilität sinkt auf strukturarmen oder stark spiegelnden Oberflächen.
- <jede weitere tatsächliche Einschränkung ergänzen — nicht glattschleifen.>

---

## Ausblick

- [ ] <nächster konkreter Schritt>
- [ ] Unreal-Engine-5-Client (der Server ist bewusst Engine-unabhängig)

---

## Lizenz

MIT — siehe [LICENSE](LICENSE).

Die referenzierten Servicehandbücher bleiben Eigentum der jeweiligen Hersteller und werden
hier **nicht mitverteilt**. `make ingest` lädt sie zur Laufzeit von der öffentlichen
Herstellerseite.

---

## Autor

**<NAME>** — Senior Engineer, XR & Spatial Computing · Augsburg
[LinkedIn](<URL>) · [E-Mail](mailto:<EMAIL>)
