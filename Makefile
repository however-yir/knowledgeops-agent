.PHONY: demo demo-verify demo-down demo-logs eval-demo

demo:
	./scripts/demo.sh

demo-verify:
	./scripts/demo.sh verify

demo-down:
	./scripts/demo.sh down

demo-logs:
	./scripts/demo.sh logs

eval-demo:
	python3 scripts/eval_demo.py
