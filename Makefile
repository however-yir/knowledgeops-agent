.PHONY: demo demo-verify demo-down demo-logs

demo:
	./scripts/demo.sh

demo-verify:
	./scripts/demo.sh verify

demo-down:
	./scripts/demo.sh down

demo-logs:
	./scripts/demo.sh logs
