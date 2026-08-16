# ar-service-assistant — developer entry points.
# Run everything from WSL2 (Ubuntu), not from PowerShell, except `make apk`.

SHELL := /bin/bash
-include .env
export

UNITY_PATH ?= /mnt/c/Program Files/Unity/Hub/Editor/6000.3.17f1/Editor/Unity.exe
UNITY_PROJECT := $(CURDIR)/unity
APK := build/ARServiceAssistant.apk

.DEFAULT_GOAL := help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- edge stack --
up: ## Start the edge stack (postgres+pgvector, api, piper)
	docker compose -f server/docker-compose.yml up -d --build
	@echo "API:     http://$(ARSA_HOST_IP):$(ARSA_PORT)/health"
	@echo "Grafana: http://localhost:3000"

down: ## Stop the edge stack
	docker compose -f server/docker-compose.yml down

logs: ## Tail the API logs
	docker compose -f server/docker-compose.yml logs -f api

# ------------------------------------------------------------------- content --
ingest: ## Download + chunk + embed the manual for $(ARSA_OBJECT)
	docker compose -f server/docker-compose.yml run --rm api \
	  python -m ingest.run --object $(ARSA_OBJECT)

eval: ## Run the retrieval/answer evaluation against the golden set
	docker compose -f server/docker-compose.yml run --rm api \
	  python -m eval.run_eval --object $(ARSA_OBJECT) --report docs/benchmarks/eval-latest.json

# --------------------------------------------------------------------- tests --
test: ## Python unit + integration tests
	docker compose -f server/docker-compose.yml run --rm api pytest -q

lint: ## ruff + mypy
	cd server && ruff check . && ruff format --check . && mypy --strict app

# --------------------------------------------------------------------- unity --
apk: ## Build the Quest APK (calls the Windows Unity editor from WSL)
	"$(UNITY_PATH)" -quit -batchmode -nographics \
	  -projectPath "$$(wslpath -w $(UNITY_PROJECT))" \
	  -executeMethod ARSA.Build.BuildScript.BuildAndroid \
	  -logFile -

install: ## adb install the APK onto the headset
	adb install -r $(APK)

# ---------------------------------------------------------------- device ops --
perf: ## Scripted device run + frame-time gate
	bash tools/perf/run_scripted_session.sh
	python tools/perf/parse_frametimes.py tools/perf/out/frametimes.json \
	  --budgets tools/perf/budgets.yaml

egress-check: ## Prove nothing left the LAN during a demo run
	bash tools/net/verify_no_egress.sh

.PHONY: help up down logs ingest eval test lint apk install perf egress-check

doctor: ## Diagnose the local environment (run this before asking for help)
	bash tools/doctor.sh

.PHONY: doctor
