.PHONY: help build up down restart logs ps clean dev queue-work

help: ## Show this help message
	@echo "RouteMQ Docker Commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

build: ## Build all Docker images
	docker compose build

up: ## Start all services (production)
	docker compose up -d

down: ## Stop all services
	docker compose down

restart: ## Restart all services
	docker compose restart

logs: ## View logs from all services
	docker compose logs -f

logs-app: ## View logs from RouteMQ app
	docker compose logs -f routemq

logs-worker: ## View logs from default queue worker
	docker compose logs -f queue-worker-default

logs-redis: ## View logs from Redis
	docker compose logs -f redis

logs-mysql: ## View logs from MySQL
	docker compose logs -f mysql

ps: ## Show running services
	docker compose ps

stats: ## Show resource usage stats
	docker stats

clean: ## Stop and remove all containers, networks, and volumes
	docker compose down -v

dev: ## Start development environment (Redis + MySQL only)
	docker compose -f docker-compose.dev.yml up -d

dev-full: ## Start development environment (all services)
	docker compose -f docker-compose.dev.yml --profile full up -d

dev-down: ## Stop development environment
	docker compose -f docker-compose.dev.yml down

queue-work: ## Start queue worker on host (for development)
	uv run python main.py --queue-work --queue default

queue-high: ## Start high-priority queue worker on host
	uv run python main.py --queue-work --queue high-priority --sleep 1

queue-emails: ## Start emails queue worker on host
	uv run python main.py --queue-work --queue emails --sleep 5

scale-default: ## Scale default queue workers to 3 instances
	docker compose up -d --scale queue-worker-default=3

scale-emails: ## Scale email queue workers to 2 instances
	docker compose up -d --scale queue-worker-emails=2

shell-app: ## Open shell in RouteMQ app container
	docker compose exec routemq bash

shell-redis: ## Open Redis CLI
	docker compose exec redis redis-cli

shell-mysql: ## Open MySQL CLI
	docker compose exec mysql mysql -uroot -p

backup-mysql: ## Backup MySQL database
	docker compose exec mysql mysqldump -uroot -p${DB_PASS} ${DB_NAME} > backup_mysql_$$(date +%Y%m%d_%H%M%S).sql

backup-redis: ## Backup Redis data
	docker compose exec redis redis-cli SAVE
	docker cp routemq-redis:/data/dump.rdb backup_redis_$$(date +%Y%m%d_%H%M%S).rdb

health: ## Check health of all services
	@echo "Service Health Status:"
	@docker compose ps --format "table {{.Service}}\t{{.Status}}"

install: ## Install dependencies on host
	uv sync

run: ## Run RouteMQ on host
	uv run python main.py --run

tinker: ## Start interactive REPL
	uv run python main.py --tinker

init: ## Initialize new RouteMQ project
	uv run python main.py --init
