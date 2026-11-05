.PHONY: help setup sync live repl voice-e2e voice-e2e-speak sim simulate sim-speak open-sim self-test doctor test lint fix check step clean

help: ## Show available root-level commands for software/ (AI Runtime) and mustang/ (3D CAD)
	@echo "1967 Ford Mustang Fastback (1:20) — Root Makefile (3D CAD 'mustang/' + AI Runtime 'software/')"
	@echo "=============================================================================================="
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: sync ## Set up Python 3.14 virtualenv in 'software/' via 'uv sync'

sync: ## Sync 'software/' Python 3.14 dependencies ('google-genai>=2.34.0', 'piper-tts', 'onnxruntime', 'pillow')
	$(MAKE) -C software sync

live: ## Launch interactive browser workbench at http://127.0.0.1:8765 (Voice -> Live Cloud Gemini -> Piper ONNX Audio + HUD + Car Control)
	$(MAKE) -C software live

repl: ## Launch interactive terminal Voice REPL with audible local Piper ONNX speech synthesis
	$(MAKE) -C software repl

voice-e2e: ## Run 4-turn end-to-end Voice -> Live Cloud Gemini -> Local Piper ONNX TTS session
	$(MAKE) -C software voice-e2e

voice-e2e-speak: ## Run 4-turn end-to-end Voice -> Live Cloud Gemini session playing local Piper ONNX audio out loud
	$(MAKE) -C software voice-e2e-speak

sim: ## Run the 4-Act Local Mac <-> Gemini Robotics ER 2.0 closed-loop simulator
	$(MAKE) -C software sim

simulate: sim ## Alias for 'make sim'

sim-speak: ## Run the 4-Act simulator with audible local Piper ONNX speech synthesis on Mac speakers
	$(MAKE) -C software sim-speak

open-sim: ## Run 'make sim' and open the generated 4-Act visual cockpit storyboard & GIF on macOS
	$(MAKE) -C software open-sim

self-test: ## Run 'mustang-ai --self-test' (FN-1, FN-2, FN-3, Watchdog, VirtualArena)
	$(MAKE) -C software self-test

doctor: ## Run 'mustang-ai doctor --harness all --mode sim'
	$(MAKE) -C software doctor HARNESS=$(or $(HARNESS),all) MODE=$(or $(MODE),sim)

test: ## Run the offline 'pytest' suite in 'software/'
	$(MAKE) -C software test

lint: ## Run 'ruff check' across both 'software/' and 'mustang/'
	$(MAKE) -C software lint

fix: ## Auto-fix lint issues across 'software/' and 'mustang/'
	$(MAKE) -C software fix

check: ## Run full verification pipeline ('sync' + 'doctor' + 'self-test' + 'sim' + 'voice-e2e' + 'test' + 'lint')
	$(MAKE) -C software check

step: ## Convert exported STLs to closed-solid STEP files for Shapr3D ('mustang/make_step.py')
	uv run mustang/make_step.py

clean: ## Clean caches in 'software/'
	$(MAKE) -C software clean
