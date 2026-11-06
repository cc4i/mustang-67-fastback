.PHONY: help setup sync live voice-live voice-verify repl voice-e2e voice-e2e-speak sim simulate sim-speak open-sim self-test doctor test lint fix check clean

PYTHON_VERSION ?= 3.14

help: ## Show available local development & simulation commands
	@echo "Mustang 67 AI Edition (v3.2.0) — Local Dev & Gemini ER 2.0 Simulator (Python $(PYTHON_VERSION))"
	@echo "=========================================================================================="
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: sync ## Alias for 'make sync' (create/update Python 3.14 .venv via uv)

sync: ## Sync Python 3.14 virtualenv and dependencies ('google-genai>=2.34.0', 'piper-tts', 'onnxruntime', 'pillow')
	uv sync --python $(PYTHON_VERSION)

live: ## Launch interactive browser workbench at http://127.0.0.1:8765 (Voice -> Live Cloud Gemini -> Piper ONNX Audio + HUD + Car Control)
	uv run mustang-ai live

voice-live: ## Launch Milestone A Radxa Voice Stack Workbench (AEC3 + Wake Word + Barge-In + S1..S7 pre-flight)
	uv run mustang-ai voice-live

voice-verify: ## Run Milestone A S1..S7 + D1..D15 voice stack verification suite and write tmp/milestone_a_voice_report.json
	uv run mustang-ai voice-live --verify-only

repl: ## Launch interactive terminal Voice REPL with audible local Piper ONNX speech synthesis
	uv run mustang-ai repl

voice-e2e: ## Run 4-turn end-to-end Voice -> Live Cloud Gemini -> Local Piper ONNX TTS session (writes WAVs + PNG + JSON)
	uv run mustang-ai voice-e2e

voice-e2e-speak: ## Run 4-turn end-to-end Voice -> Live Cloud Gemini session playing local Piper ONNX audio out loud on Mac speakers
	uv run mustang-ai voice-e2e --speak-mac

sim: ## Run the 4-Act Local Mac <-> Gemini Robotics ER 2.0 closed-loop simulator (generates PNG + GIF + JSON)
	uv run mustang-ai simulate

simulate: sim ## Alias for 'make sim'

sim-speak: ## Run the 4-Act simulator with audible local Piper ONNX speech synthesis on Mac speakers
	uv run mustang-ai simulate --speak-mac

open-sim: sim ## Run 'make sim' and open the generated 4-Act visual cockpit storyboard & GIF on macOS
	open ../docs/images/ai_gemini_er_mac_simulation.png ../docs/images/ai_gemini_er_mac_simulation.gif

self-test: ## Run deterministic E2E self-test and generate 12-emoji GC9A01 sheet + runtime report
	uv run mustang-ai --self-test

doctor: ## Run H1..H5 cable harness hardware/simulation diagnostics ('HARNESS=all' by default)
	uv run mustang-ai doctor --harness $(or $(HARNESS),all) --mode $(or $(MODE),sim)

test: ## Run the offline pytest verification suite
	uv run pytest -v

lint: ## Run ruff linter across 'software/' and '../mustang/'
	uv run ruff check --select E,F,W --ignore E731 --line-length 140 . ../mustang

fix: ## Auto-fix lint issues with ruff
	uv run ruff check --fix --select E,F,W --ignore E731 --line-length 140 . ../mustang

check: sync doctor self-test sim voice-e2e test lint ## Run full local verification pipeline (sync + doctor + self-test + sim + voice-e2e + test + lint)

clean: ## Remove local test/lint caches ('__pycache__', '.pytest_cache', '.ruff_cache')
	rm -rf .pytest_cache .ruff_cache
	find . -type d -name "__pycache__" -exec rm -rf {} +
