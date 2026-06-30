.PHONY: help up down build logs clean restart status seed-demo seed-recalculate

help:
	@echo "Available commands:"
	@echo "  make up                  - Start all services in the background (db, redis, app, simulator)"
	@echo "  make down                - Stop and remove all containers"
	@echo "  make build               - Build or rebuild Docker images"
	@echo "  make logs                - View logs for all running services"
	@echo "  make clean               - Stop services and remove all volumes (data reset)"
	@echo "  make restart             - Restart application container"
	@echo "  make status              - Show status of all containers"
	@echo "  make seed-demo           - Insert demo seed data into PostgreSQL"
	@echo "  make seed-recalculate    - Trigger manual recalculation of risk profiling zones"

up:
	docker compose up -d --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

clean:
	docker compose down -v

restart:
	docker compose restart app

status:
	docker compose ps

seed-demo:
	docker compose exec -T postgres psql -U traffic_user -d traffic_db < backend/scripts/seed_demo_data.sql

seed-recalculate:
	curl -X POST http://localhost:8000/api/analytics/risk-zones/recalculate
