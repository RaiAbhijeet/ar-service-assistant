# CLAUDE.md — ar-service-assistant

Read this file completely before touching any code. It is the contract.

---

## 1. What this project is

An **offline AR maintenance assistant**. A Meta Quest 3S looks at a real physical object
through its passthrough camera, identifies the component in view, and overlays step-by-step
instructions retrieved from the manufacturer's own service manual. **All inference runs on a
local edge server on the same LAN. Nothing ever leaves the local network.**

- **Headset (Quest 3S)** = thin client. Captures camera frames + microphone, renders UI, plays audio.
- **Edge server (Dell Precision 7730, Windows 11 + WSL2, Quadro P5200 16 GB)** = all inference.
- **Transport** = WebSocket over LAN.

The demo object is **configurable** (see `objects/`). The default is a bicycle drivetrain.
No code may hardcode anything about a specific object.

---

## 2. Hard constraints — never violate these

### Privacy / architecture
- **NO cloud API calls in runtime code.** No `openai`, `anthropic`, `google-generativeai`,
  `azure-*`, `boto3` or any hosted-inference SDK may appear in `server/app/` or `unity/`.
- The Docker network for the runtime stack has no default route. If you need to add a service
  that requires internet access, stop and ask — it is almost certainly wrong.
- Ingestion (`server/ingest/`) is the one place that downloads from the internet. It runs
  offline-of-the-demo, as a separate step, and never at request time.

### Inference
- Inference backend is **Ollama / llama.cpp only**. Do **not** introduce vLLM, TensorRT-LLM,
  or SGLang — they require CUDA compute capability ≥ 7.0 and the target GPU is 6.1 (Pascal).
- Quantization is **Q4_K_M or Q5_K_M**. Never configure an FP16 inference path: Pascal runs
  FP16 at 1/64 rate. See `docs/adr/0004-*`.
- `OLLAMA_FLASH_ATTENTION` stays **off**. Do not enable it "for performance".
- One model serves both vision and text. Do not load a second LLM alongside the VLM.

### Orchestration
- The orchestrator is an **explicit finite state machine** in `server/app/orchestrator/fsm.py`.
- Do **not** introduce LangChain, LangGraph, CrewAI, AutoGen, LlamaIndex or any agent framework.
  A maintenance procedure is a state machine, and in a regulated context it must be
  deterministic and auditable. This is a deliberate architectural decision, not an oversight.

### Unity
- **OpenXR plugin**, not the legacy Oculus XR plugin.
- URP. Single-Pass Instanced rendering. IL2CPP. ARM64 only.
- **Zero heap allocations in per-frame code paths.** Use `UniTask` (never `async void`,
  never allocating coroutines in `Update`), `NativeArray`, and object pooling.
  Any PR touching a per-frame path must include an allocation test.
- No `GameObject.Find`, no `Camera.main` in `Update`, no `GetComponent` in `Update`.
- All Unity assemblies use Assembly Definition files with the prefix `ARSA.`.

### Safety behaviour (this is a feature, not a nicety)
- The system must **refuse** rather than guess. If part-recognition confidence is below the
  configured threshold, respond "Ich bin nicht sicher — bitte näher herangehen" and do not
  produce an instruction.
- If retrieval returns nothing above the score threshold, respond
  "Dazu finde ich im Handbuch nichts" and do not generate an answer from model priors.
- Never fabricate a torque value, part number, or step order. Every instruction must be
  traceable to a retrieved chunk, and the chunk's page number must be shown in the UI.

### Language
- All user-facing strings are **German first**, English fallback, via a resource file
  (`unity/Assets/Resources/Strings/`). Never hardcode a user-facing string in code.
- Code, comments, commit messages, ADRs and the primary README are in **English**.
- `README.de.md` is the German translation and must be updated in the same commit as `README.md`.

---

## 3. Repository layout

```
ar-service-assistant/
├── CLAUDE.md                  # this file
├── README.md  README.de.md  LICENSE  CHANGELOG.md  Makefile
├── objects/<object-id>/       # demo object definitions (config, not code)
│   ├── object.yaml            # parts, manual source URL + sha256, thresholds
│   └── reference/<part-id>/   # reference photos for few-shot recognition
├── server/
│   ├── app/
│   │   ├── api/               # FastAPI routes, WebSocket handler
│   │   ├── orchestrator/      # the FSM. the heart of the system.
│   │   ├── vision/            # part recognition
│   │   ├── retrieval/         # hybrid BM25 + dense, RRF
│   │   ├── stt/  tts/         # whisper.cpp, piper wrappers
│   │   ├── telemetry/         # OpenTelemetry, Prometheus
│   │   └── config.py          # pydantic-settings, all config from env/yaml
│   ├── ingest/                # manual download + chunk + embed (offline step)
│   ├── eval/                  # golden_de.yaml, run_eval.py, thresholds.yaml
│   ├── tests/{unit,integration,eval}/
│   ├── docker-compose.yml  Dockerfile  pyproject.toml
├── unity/                     # Unity 6 project (Assets, Packages, ProjectSettings only)
├── tools/perf/                # frame-time capture + CI gate
├── tools/net/                 # zero-egress verification
├── docs/{adr,benchmarks,demo,logbook}/
└── .github/workflows/
```

---

## 4. Definition of Done — applies to every task

A task is not done until **all** of these hold:

- [ ] Unit tests written and passing
- [ ] `ruff check` and `ruff format --check` clean
- [ ] `mypy --strict` clean on `server/app/`
- [ ] No new compiler warnings on the Unity side
- [ ] If it touches a per-frame path: an allocation test exists and asserts 0 bytes
- [ ] If it touches retrieval or prompts: `make eval` run, and Recall@5 has not regressed
- [ ] If it adds a dependency: an ADR exists explaining why
- [ ] The relevant section of `README.md` **and** `README.de.md` updated
- [ ] Conventional Commit message

---

## 5. Commands

```
make up          # start the edge stack (ollama, postgres+pgvector, api, piper)
make down        # stop it
make ingest      # download + chunk + embed the manual for the active object
make eval        # run the retrieval/answer evaluation against the golden set
make test        # python tests
make apk         # build the Unity APK
make install     # adb install the APK
make perf        # scripted device run + frame-time gate
make egress-check# tcpdump verification that nothing left the LAN
make lint        # ruff + mypy
```

Active object is selected by `ARSA_OBJECT` in `.env` (default: `bike-drivetrain`).

---

## 6. How I want you to work

1. **Plan before editing.** When given a task, first list the files you will create or modify
   and why, in one short block. Wait for my confirmation. Do not start editing.
2. **One vertical slice at a time.** Every task must end with something I can actually run.
   Never "build all the Python, then all the Unity."
3. **Small diffs.** If a change touches more than ~6 files, split it and tell me.
4. **No speculative abstraction.** No base classes, plugin systems or config layers that have
   exactly one implementation. Add the second implementation first, then abstract.
5. **When a constraint in section 2 blocks the obvious solution, stop and say so.** Do not
   quietly work around it. The constraints exist for reasons documented in `docs/adr/`.
6. **Do not write the golden evaluation set.** `server/eval/golden_de.yaml` is written by hand
   by the repo owner. You may add schema validation for it, never entries.
7. **Do not invent measurements.** Never write a number into README, CHANGELOG or an ADR that
   did not come from an actual run. If a metric is not yet measured, write `TBD`.

---

## 7. Coding standards

**Python 3.12.** FastAPI + Pydantic v2. `pydantic-settings` for config — no bare `os.environ`
outside `config.py`. Structured logging (`structlog`) with a `trace_id` on every request.
Type hints everywhere; `mypy --strict`. Prefer `httpx.AsyncClient` (LAN only). Tests use
`pytest` + `pytest-asyncio`; no network in unit tests, all external services faked.

**C# / Unity 6.** `ARSA.*` assembly definitions. `UniTask` for async. `System.Buffers`
pooling for frame buffers. All configuration through a `ScriptableObject`, never constants in
`MonoBehaviour`. Interfaces at the seams (`ICameraProvider`, `ITransport`, `ISpeechInput`) so
the client is testable in EditMode without a headset.

---

## 8. Things that will be tested in a job interview

The repo owner has to be able to explain every line of this codebase in a whiteboard
interview. Therefore:

- Prefer boring, explicit code over clever code.
- Every non-obvious decision gets an ADR at the moment it is made.
- If you generate something the owner has not asked about and cannot be expected to
  understand at a glance, say so explicitly in your summary.
