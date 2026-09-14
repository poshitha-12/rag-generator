.PHONY: verify test lint no-hardcoded no-heavy-deps docker-smoke eval

# Single entry point for the agent (or you) to check the build against
# SPEC.md. Run this after every meaningful change and keep iterating
# until it's green — that's the whole point of a harness: fast,
# unambiguous, machine-checkable feedback instead of manual eyeballing.
verify: test lint no-hardcoded no-heavy-deps docker-smoke
	@echo "Automated checks passed. Remaining items are the manual ones in SPEC.md's Definition of Done."

test:
	pytest -q

lint:
	ruff check app/

# NFR3 / FR1 / FR7 — fails if any sample document name leaks into app logic.
# Extend this list if you add differently-named sample data.
no-hardcoded:
	@! grep -rEi "handbook|faq" app/ && echo "OK: no hardcoded sample document references in app/"

# NFR5 — embedding and reranking both run on FastEmbed's ONNX runtime. A
# PyTorch-backed equivalent (sentence-transformers, a bare CrossEncoder)
# works but drags in a ~1GB+ torch/CUDA download and a much slower image
# build, so the build fails if one appears in requirements.txt.
no-heavy-deps:
	@! grep -rEi "^(torch|torchvision|torchaudio|tensorflow|nvidia-|.*-cuda|sentence-transformers|transformers)\b" requirements.txt \
		&& echo "OK: no torch/tensorflow/cuda dependencies in requirements.txt"

# NFR1 — confirms the whole stack actually comes up from a clean state,
# not just that individual functions work.
docker-smoke:
	docker compose up --build -d
	sleep 8
	curl -sf http://localhost:8501/_stcore/health || (docker compose logs && docker compose down && exit 1)
	docker compose down

# NFR4 — answer quality against the real LLM. Deliberately NOT part of
# `verify`: it needs a live API key and spends tokens, and verify should
# stay free and key-independent.
eval:
	python eval/run_eval.py
