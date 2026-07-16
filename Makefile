all: deploy

# --- First-time setup (no Docker required) ---
setup:
	@echo "Creating CodeBuild infrastructure..."
	./scripts/run_codebuild.sh setup

# --- Deploy via CodeBuild (runs entirely in AWS) ---
deploy:
	./scripts/run_codebuild.sh deploy

synth:
	./scripts/run_codebuild.sh synth

status:
	./scripts/run_codebuild.sh status

logs:
	./scripts/run_codebuild.sh logs

# --- Destroy ---
destroy:
	./scripts/run_codebuild.sh destroy

cleanup:
	./scripts/run_codebuild.sh cleanup

# --- Local development ---
test: install-python
	. venv/bin/activate && pytest -vv

test-update: install-python
	. venv/bin/activate && pytest --snapshot-update

install-python: venv/touchfile
venv/touchfile: requirements.txt
	@echo "Creating virtual environment..."
	python3 -m venv venv
	@echo "Installing Python requirements..."
	. venv/bin/activate && pip install -r requirements.txt
	touch venv/touchfile

clean:
	@echo "Removing virtual environment and node modules..."
	rm -rf venv node_modules
