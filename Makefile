PYTHON := /opt/homebrew/bin/python3
VENV_PY := .venv/bin/python
VENV_PIP := .venv/bin/pip
API_BASE ?= http://127.0.0.1:8000/api
FLY_APP ?= askbhagavadgita
CURL_OPTS := --connect-timeout 3 --max-time 15

.PHONY: setup setup-lock install install-lock run migrate makemigrations test lock convert-gita-csv ingest-gita-multiscript import-gita tag-gita-themes embed-gita-verses setup-pgvector-index sync-pgvector-embeddings eval-retrieval auth-flow auth-flow-benchmark auth-flow-benchmark-summary fly-redis-smoke fly-cache-smoke clean

setup:
	$(PYTHON) -m venv .venv
	$(VENV_PIP) install -r requirements.txt
	$(VENV_PY) manage.py migrate

setup-lock:
	$(PYTHON) -m venv .venv
	$(VENV_PIP) install -r requirements.lock.txt
	$(VENV_PY) manage.py migrate

install:
	$(VENV_PIP) install -r requirements.txt

install-lock:
	$(VENV_PIP) install -r requirements.lock.txt

run:
	$(VENV_PY) manage.py runserver

migrate:
	$(VENV_PY) manage.py migrate

makemigrations:
	$(VENV_PY) manage.py makemigrations

test:
	$(VENV_PY) manage.py test

lock:
	$(VENV_PIP) freeze > requirements.lock.txt

convert-gita-csv:
	@if [ -z "$(INPUT)" ]; then echo "Usage: make convert-gita-csv INPUT=data/Bhagwad_Gita.csv"; exit 1; fi
	$(VENV_PY) scripts/convert_kaggle_gita_csv.py --input "$(INPUT)" --output data/gita_700.json

ingest-gita-multiscript:
	@if [ -z "$(INPUT)" ]; then echo "Usage: make ingest-gita-multiscript INPUT=/path/bhagavad-gita.xlsx"; exit 1; fi
	$(VENV_PY) manage.py ingest_gita_multiscript --input "$(INPUT)"

import-gita:
	@if [ -z "$(FILE)" ]; then echo "Usage: make import-gita FILE=data/gita_700.json"; exit 1; fi
	$(VENV_PY) manage.py import_gita --file "$(FILE)"

tag-gita-themes:
	$(VENV_PY) manage.py tag_gita_themes

embed-gita-verses:
	$(VENV_PY) manage.py embed_gita_verses

setup-pgvector-index:
	$(VENV_PY) manage.py setup_pgvector_index

sync-pgvector-embeddings:
	$(VENV_PY) manage.py sync_pgvector_embeddings

eval-retrieval:
	$(VENV_PY) manage.py eval_retrieval --file data/retrieval_eval_cases.json --mode pipeline

auth-flow:
	@if [ -z "$(USERNAME)" ]; then echo "Usage: make auth-flow USERNAME=demo-user PASSWORD=demo-pass-123"; exit 1; fi
	@if [ -z "$(PASSWORD)" ]; then echo "Usage: make auth-flow USERNAME=demo-user PASSWORD=demo-pass-123"; exit 1; fi
	@$(VENV_PY) manage.py migrate --check >/dev/null 2>&1 || (echo "Unapplied migrations detected. Run: make migrate"; exit 1)
	@echo "Registering user (safe to fail if user already exists)..."
	@curl -sS $(CURL_OPTS) -X POST "$(API_BASE)/auth/register/" -H "Content-Type: application/json" -d "{\"username\":\"$(USERNAME)\",\"password\":\"$(PASSWORD)\"}" || true
	@echo
	@echo "Logging in and capturing token..."
	@LOGIN_RESPONSE=$$(curl -sS $(CURL_OPTS) -X POST "$(API_BASE)/auth/login/" -H "Content-Type: application/json" -d "{\"username\":\"$(USERNAME)\",\"password\":\"$(PASSWORD)\"}" 2>&1); \
	CURL_EXIT=$$?; \
	if [ $$CURL_EXIT -ne 0 ]; then \
		echo "Login request failed. Is the server running at $(API_BASE)?"; \
		echo "$$LOGIN_RESPONSE"; \
		exit 1; \
	fi; \
	TOKEN=$$(printf "%s" "$$LOGIN_RESPONSE" | $(VENV_PY) scripts/extract_token.py); \
	if [ -z "$$TOKEN" ]; then \
		echo "Login failed. Unexpected response:"; \
		echo "$$LOGIN_RESPONSE"; \
		exit 1; \
	fi; \
	echo "Token acquired."; \
	echo "Calling /auth/me"; \
	curl -sS $(CURL_OPTS) "$(API_BASE)/auth/me/" -H "Authorization: Token $$TOKEN"; echo; \
	echo "Calling /ask"; \
	curl -sS $(CURL_OPTS) -X POST "$(API_BASE)/ask/" -H "Authorization: Token $$TOKEN" -H "Content-Type: application/json" -d '{"message":"I am anxious about my career growth.","mode":"simple"}'; echo; \
	echo "Calling /history/me"; \
	curl -sS $(CURL_OPTS) "$(API_BASE)/history/me/" -H "Authorization: Token $$TOKEN"; echo; \
	echo "Calling /auth/logout"; \
	curl -sS $(CURL_OPTS) -X POST "$(API_BASE)/auth/logout/" -H "Authorization: Token $$TOKEN"; echo

auth-flow-benchmark:
	@if [ -z "$(USERNAME)" ]; then echo "Usage: make auth-flow-benchmark USERNAME=demo-user PASSWORD=demo-pass-123"; exit 1; fi
	@if [ -z "$(PASSWORD)" ]; then echo "Usage: make auth-flow-benchmark USERNAME=demo-user PASSWORD=demo-pass-123"; exit 1; fi
	@$(VENV_PY) manage.py migrate --check >/dev/null 2>&1 || (echo "Unapplied migrations detected. Run: make migrate"; exit 1)
	@echo "Registering user (safe to fail if user already exists)..."
	@curl -sS $(CURL_OPTS) -X POST "$(API_BASE)/auth/register/" -H "Content-Type: application/json" -d "{\"username\":\"$(USERNAME)\",\"password\":\"$(PASSWORD)\"}" || true
	@echo
	@echo "Logging in and capturing token..."
	@LOGIN_RESPONSE=$$(curl -sS $(CURL_OPTS) -X POST "$(API_BASE)/auth/login/" -H "Content-Type: application/json" -d "{\"username\":\"$(USERNAME)\",\"password\":\"$(PASSWORD)\"}" 2>&1); \
	CURL_EXIT=$$?; \
	if [ $$CURL_EXIT -ne 0 ]; then \
		echo "Login request failed. Is the server running at $(API_BASE)?"; \
		echo "$$LOGIN_RESPONSE"; \
		exit 1; \
	fi; \
	TOKEN=$$(printf "%s" "$$LOGIN_RESPONSE" | $(VENV_PY) scripts/extract_token.py); \
	if [ -z "$$TOKEN" ]; then \
		echo "Login failed. Unexpected response:"; \
		echo "$$LOGIN_RESPONSE"; \
		exit 1; \
	fi; \
	echo "Token acquired."; \
	echo "Calling /eval/retrieval in benchmark mode"; \
	curl -sS $(CURL_OPTS) -X POST "$(API_BASE)/eval/retrieval/" -H "Authorization: Token $$TOKEN" -H "Content-Type: application/json" -d '{"message":"I am anxious about career growth and performance.","mode":"benchmark"}'; echo; \
	echo "Calling /ask"; \
	curl -sS $(CURL_OPTS) -X POST "$(API_BASE)/ask/" -H "Authorization: Token $$TOKEN" -H "Content-Type: application/json" -d '{"message":"I am anxious about my career growth.","mode":"simple"}'; echo; \
	echo "Calling /auth/logout"; \
	curl -sS $(CURL_OPTS) -X POST "$(API_BASE)/auth/logout/" -H "Authorization: Token $$TOKEN"; echo

auth-flow-benchmark-summary:
	@if [ -z "$(USERNAME)" ]; then echo "Usage: make auth-flow-benchmark-summary USERNAME=demo-user PASSWORD=demo-pass-123"; exit 1; fi
	@if [ -z "$(PASSWORD)" ]; then echo "Usage: make auth-flow-benchmark-summary USERNAME=demo-user PASSWORD=demo-pass-123"; exit 1; fi
	@$(VENV_PY) manage.py migrate --check >/dev/null 2>&1 || (echo "Unapplied migrations detected. Run: make migrate"; exit 1)
	@echo "Registering user (safe to fail if user already exists)..."
	@curl -sS $(CURL_OPTS) -X POST "$(API_BASE)/auth/register/" -H "Content-Type: application/json" -d "{\"username\":\"$(USERNAME)\",\"password\":\"$(PASSWORD)\"}" || true
	@echo
	@echo "Logging in and capturing token..."
	@LOGIN_RESPONSE=$$(curl -sS $(CURL_OPTS) -X POST "$(API_BASE)/auth/login/" -H "Content-Type: application/json" -d "{\"username\":\"$(USERNAME)\",\"password\":\"$(PASSWORD)\"}" 2>&1); \
	CURL_EXIT=$$?; \
	if [ $$CURL_EXIT -ne 0 ]; then \
		echo "Login request failed. Is the server running at $(API_BASE)?"; \
		echo "$$LOGIN_RESPONSE"; \
		exit 1; \
	fi; \
	TOKEN=$$(printf "%s" "$$LOGIN_RESPONSE" | $(VENV_PY) scripts/extract_token.py); \
	if [ -z "$$TOKEN" ]; then \
		echo "Login failed. Unexpected response:"; \
		echo "$$LOGIN_RESPONSE"; \
		exit 1; \
	fi; \
	echo "Token acquired."; \
	echo "Benchmark summary:"; \
	curl -sS $(CURL_OPTS) -X POST "$(API_BASE)/eval/retrieval/" -H "Authorization: Token $$TOKEN" -H "Content-Type: application/json" -d '{"message":"I am anxious about career growth and performance.","mode":"benchmark"}' | $(VENV_PY) scripts/print_retrieval_benchmark_summary.py; \
	echo "Calling /auth/logout"; \
	curl -sS $(CURL_OPTS) -X POST "$(API_BASE)/auth/logout/" -H "Authorization: Token $$TOKEN"; echo

fly-redis-smoke:
	@echo "Running Redis smoke check on Fly app: $(FLY_APP)"
	@fly ssh console --app $(FLY_APP) --command "python -c \"import os,redis; u=os.getenv('REDIS_URL',''); print('HAS_REDIS_URL=', bool(u)); print('SCHEME=', u.split('://')[0] if '://' in u else 'missing'); r=redis.from_url(u, socket_connect_timeout=5, socket_timeout=5); print('PING=', r.ping()); r.set('smoke:fly','ok',ex=30); print('GET=', r.get('smoke:fly'))\""

fly-cache-smoke:
	@echo "Running Django cache smoke check on Fly app: $(FLY_APP)"
	@fly ssh console --app $(FLY_APP) --command "python -c \"import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); import django; django.setup(); from django.core.cache import cache; cache.set('smoke:cache','ok',30); print('CACHE_GET=', cache.get('smoke:cache'))\""

clean:
	rm -rf .venv
