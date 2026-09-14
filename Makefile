.PHONY: verify test lint no-hardcoded docker-smoke

# Single entry point for the agent (or you) to check the build against
# SPEC.md. Run this after every meaningful change and keep iterating
# until it's green — that's the whole point of a harness: fast,
# unambiguous, machine-checkable feedback instead of manual eyeballing.
verify: test lint no-hardcoded docker-smoke
	@echo "Automated checks passed. Remaining items are the manual ones in SPEC.md's Definition of Done."

test:
	pytest -q

lint:
	ruff check app/

# NFR3 / FR1 / FR7 — fails if any sample document name leaks into app logic.
# Extend this list if you add differently-named sample data.
no-hardcoded:
	@! grep -rEi "handbook|faq" app/ && echo "OK: no hardcoded sample document references in app/"

# NFR1 — confirms the whole stack actually comes up from a clean state,
# not just that individual functions work.
docker-smoke:
	docker compose up --build -d
	sleep 8
	curl -sf http://localhost:8501/_stcore/health || (docker compose logs && docker compose down && exit 1)
	docker compose down
