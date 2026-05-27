.PHONY: up down logs ps run queue-work

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

ps:
	docker compose ps

run:
	routemq run

queue-work:
	routemq queue-work --queue default
