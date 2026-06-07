.PHONY: dev backend frontend

dev:
	@echo "Starting backend and frontend..."
	@make -j 2 backend frontend

backend:
	cd backend && ~/.local/bin/uv run uvicorn src.main:app --reload --port 8001

frontend:
	cd frontend && npm run dev
