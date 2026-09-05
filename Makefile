all: deploy

# --- First-time setup (no Docker required) ---
setup: install-python install-node
	@echo "Creating CodeBuild infrastructure..."
	./scripts/run_codebuild.sh setup

# --- Deploy via CodeBuild (runs entirely in AWS, no local Docker) ---
deploy:
	./scripts/run_codebuild.sh deploy

synth:
	./scripts/run_codebuild.sh synth

status:
	./scripts/run_codebuild.sh status

logs:
	./scripts/run_codebuild.sh logs

# --- Local deploy (requires Docker or Finch) ---
local-deploy: install-python install-node
	@echo "Running local cdk deploy..."
	. venv/bin/activate && npx cdk deploy --require-approval never

local-synth: install-python install-node
	@echo "Running local cdk synth..."
	. venv/bin/activate && npx cdk synth --quiet

local-bootstrap: install-python install-node
	@echo "Running cdk bootstrap..."
	. venv/bin/activate && npx cdk bootstrap

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

install-node: node_modules
node_modules: package.json package-lock.json
	@echo "Installing Node.js requirements..."
	npm install

clean:
	@echo "Removing virtual environment and node modules..."
	rm -rf venv node_modules
