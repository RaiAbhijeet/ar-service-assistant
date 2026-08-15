<!--
  README TEMPLATE — replace every <PLACEHOLDER> and every "TBD" as the project progresses.
  Do not invent numbers. A "TBD" is honest; a wrong number is not.
  German version: README.de.md  (must be updated in the same commit)
-->

# AR Service Assistant

**Mixed-reality maintenance assistance that runs entirely on-premise.**
Point a Meta Quest 3S at a piece of equipment. It recognises the component through the
passthrough camera, retrieves the matching procedure from the manufacturer's own service
manual, and overlays the steps in place — spoken and written, in German. No cloud. No data
leaves the local network.

🇩🇪 [Deutsche Version](README.de.md)

<!-- The demo GIF goes here, ABOVE all remaining text. 8 seconds, autoplay, <5 MB. -->
![demo](docs/demo/demo.gif)

---

## Why

Maintenance technicians in aerospace, rail, energy and manufacturing work under two
constraints at once:

1. **Their hands are busy and the manual is 400 pages.** Looking up a procedure means putting
   down tools and losing the work position.
2. **Plant and equipment data may not leave the site.** Cloud assistants are not an option —
   not for compliance reasons that can be negotiated, but for contractual ones that cannot.

Existing AR maintenance tools solve (1) and ignore (2), or solve (2) by having no AI at all.
This project does both: a vision-language model and a retrieval pipeline running on a single
on-premise machine, with the headset as a thin client.

---

## Results

<!-- Fill each row from an actual measured run. Keep TBD until measured. -->

| Metric | Target | Measured |
|---|---|---|
| Retrieval Recall@5 (German golden set, n=40) | ≥ 0.85 | TBD |
| Answer faithfulness (judge + manual audit) | ≥ 0.90 | TBD |
| Part recognition top-1 (n=120, 3 lighting conditions) | ≥ 0.90 | TBD |
| **False-confident rate** (wrong part at confidence > 0.8) | ≤ 0.02 | TBD |
| Time to first token (p95) | ≤ 1.5 s | TBD |
| End-to-end to first audio (p95) | ≤ 2.5 s | TBD |
| Frame time p95 @ 72 Hz | ≤ 13.9 ms | TBD |
| GC allocations per frame, steady state | 0 B | TBD |
| Thermal throttle onset | > 15 min | TBD |
| Peak VRAM | < 14 GB | TBD |
| **Bytes egressed during a full demo run** | **0** | TBD |
| Cold start (`make up` → first answer) | < 90 s | TBD |

Raw captures and plots: [`docs/benchmarks/`](docs/benchmarks/)

---

## Architecture

![architecture](docs/architecture.png)

```
Meta Quest 3S  ──  thin client
  Passthrough Camera API ─► JPEG frame (640×480) ─┐
  Microphone ─► 16 kHz PCM ───────────────────────┤  WebSocket / LAN
  Spatial anchor + step panel + TTS audio ◄───────┘
                                │
Edge server (Dell Precision 7730 · Quadro P5200 16 GB · WSL2)
  FastAPI  →  FSM orchestrator
      ├─ whisper.cpp            speech → text (de)
      ├─ Ollama / llama.cpp     Qwen3-VL, Q4_K_M — part ID + answer generation
      ├─ Postgres + pgvector    manual chunks, hybrid BM25 + dense retrieval
      └─ Piper                  text → speech (de)
  Prometheus + Grafana          throughput, latency, VRAM, GPU temperature
  Docker network with no default route
```

Full detail: [`docs/architecture.md`](docs/architecture.md)

---

## Engineering decisions

Each of these is a documented trade-off, not a default:

| ADR | Decision |
|---|---|
| [0001](docs/adr/0001-edge-inference-instead-of-on-device.md) | Inference on an edge server, not on the headset — with the measurements that ruled on-device out |
| [0002](docs/adr/0002-explicit-fsm-instead-of-agent-framework.md) | An explicit finite state machine instead of an agent framework |
| [0003](docs/adr/0003-rag-instead-of-finetuning.md) | Retrieval over the real manual instead of fine-tuning |
| [0004](docs/adr/0004-int4-quantization-no-fp16-on-pascal.md) | Integer quantization only — no FP16 path on Pascal hardware |
| [0005](docs/adr/0005-openxr-instead-of-vendor-plugin.md) | OpenXR instead of the vendor XR plugin |
| [0006](docs/adr/0006-refusal-over-generation.md) | Refusing to answer is a first-class outcome |

---

## Quickstart

**Requirements:** Windows 11 + WSL2 (or Linux), NVIDIA GPU with compute capability ≥ 5.0 and
driver ≥ 550, Docker, Unity 6 LTS with Android Build Support, a Meta Quest 3 / 3S in
developer mode.

```bash
git clone https://github.com/<USER>/ar-service-assistant
cd ar-service-assistant
cp .env.example .env          # set ARSA_OBJECT and ARSA_HOST_IP

make up                        # start the edge stack
curl http://$ARSA_HOST_IP:$ARSA_PORT/health   # confirm the API + DB are reachable
make ingest                    # fetch + chunk + embed the service manual
make eval                      # verify retrieval quality before you trust it

make apk && make install       # build and deploy to the headset
```

The service manual is **not** included in this repository. `make ingest` downloads it from the
manufacturer's public support site and verifies the SHA-256 recorded in
`objects/<object>/object.yaml`.

---

## Adding a new object

No code changes required:

```
objects/my-machine/
├── object.yaml            # part list, manual URL + sha256, confidence thresholds
└── reference/<part-id>/   # ~20 reference photos per part
```

Then `ARSA_OBJECT=my-machine make ingest`.

Objects currently shipped: `bike-drivetrain` (primary), `<second-object>` (proves the
config-driven claim).

---

## Hardware

Developed and measured on hardware deliberately chosen to be modest, because on-premise
inference boxes in a plant are modest:

| | |
|---|---|
| Edge server | Dell Precision 7730 — i7-8850H, 64 GB RAM, **NVIDIA Quadro P5200 16 GB (Pascal, CC 6.1)** |
| Headset | Meta Quest 3S (Snapdragon XR2 Gen 2, 8 GB) |
| Network | LAN, 5 GHz Wi-Fi |

Pascal has no tensor cores and runs FP16 at 1/64 rate, so the inference path is
integer-quantized throughout. See [ADR-0004](docs/adr/0004-int4-quantization-no-fp16-on-pascal.md).

---

## On-device inference: measured and rejected

Running the language model on the headset itself was evaluated and rejected. The reference
study [LoXR (arXiv:2502.15761)](https://arxiv.org/abs/2502.15761) measured a Meta Quest 3 at
**5.77 tokens/s** generation with **9.7 % battery drain per 10 minutes**, ranking last among
four XR devices tested.

This repository extends those measurements to the **Quest 3S**, and adds the two metrics LoXR
did not report — **time to first token** and **frame-time impact while a scene is rendering**:
[`quest-llm-bench`](https://github.com/<USER>/quest-llm-bench) · results in
[`docs/benchmarks/on-device.md`](docs/benchmarks/on-device.md).

Edge inference is also simply the correct industrial architecture. No plant runs inference on
a technician's headset; they run a box in the hall.

---

## Limitations

<!-- Keep this section honest and specific. It raises credibility more than any other section. -->

- Recognition is a **closed set** of the parts defined in `object.yaml`. Unknown parts are
  refused, not guessed.
- Requires a LAN connection to the edge server. There is no on-device fallback (by design —
  see the section above).
- Tested only in indoor lighting between <X> and <Y> lux.
- German only. English strings exist but are untested against a golden set.
- Anchor stability degrades on featureless or highly reflective surfaces.
- <add every real limitation you find. Do not sand them off.>

---

## Roadmap

- [ ] <next concrete thing>
- [ ] Unreal Engine 5 client (the server is engine-agnostic by design)

---

## Licence

MIT — see [LICENSE](LICENSE).

Service manuals referenced by this project remain the property of their respective
manufacturers and are **not redistributed here**. `make ingest` fetches them from the
manufacturer's public site at build time.

---

## Author

**<NAME>** — Senior Engineer, XR & Spatial Computing · Augsburg, Germany
[LinkedIn](<URL>) · [Email](mailto:<EMAIL>)
