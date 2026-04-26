.PHONY: setup test test-one rescore rescore-one validate-judge help

# Install all dependencies (agent + eval framework)
setup:
	pip install -r requirements.txt -r requirements-eval.txt

# Run the full evaluation suite (calls agent, saves traces + report)
test:
	python eval_run.py

# Run a single case file — usage: make test-one CASE=cases/01_happy_voyager.yaml
test-one:
	python eval_run.py --cases $(CASE)

# Re-score all existing traces without calling the agent
rescore:
	python eval_run.py --rescore-all

# Re-score one trace — usage: make rescore-one TRACE=traces/<id>.json CASE=cases/01_happy_voyager.yaml
rescore-one:
	python eval_run.py --rescore $(TRACE) --case $(CASE)

# Spot-check LLM judge verdicts by hand (prints each verdict + rationale)
validate-judge:
	python -m eval.validate_judge

# Diff against a specific prior report — usage: make diff PREV=reports/<id>.json
diff:
	python eval_run.py --rescore-all --prev-report $(PREV)

help:
	@echo ""
	@echo "  make setup                            install dependencies"
	@echo "  make test                             run full suite (calls agent)"
	@echo "  make test-one CASE=cases/01_...yaml  run a single case"
	@echo "  make rescore                          re-score all traces (no agent calls)"
	@echo "  make rescore-one TRACE=... CASE=...  re-score one trace"
	@echo "  make validate-judge                  spot-check judge verdicts"
	@echo "  make diff PREV=reports/<id>.json     diff against a prior run"
	@echo ""
