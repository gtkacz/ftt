image_name=ftt
PWD=$(shell pwd)

setup:
	@python -m venv venv
	@source venv/bin/activate
	@pip install --upgrade pip
	@pip install -r requirements.txt
	@pip install pre-commit
	@pre-commit install
	@cp .env.template .env

docs:
	@docker exec -it $(image_name)-container python manage.py spectacular --color --file schema.yml

run-local:
	@python manage.py runserver

build:
	@docker build --tag $(image_name) .
	@docker image prune -f

run:
	@docker run -v $(PWD):/app --rm -it -p 8000:8000 --name $(image_name)-container $(image_name)

run-detached:
	@docker run -v $(PWD):/app --rm -it -p 8000:8000 -d --name $(image_name)-container $(image_name)

stop:
	@docker stop $(image_name)-container

migrations:
	@docker exec -it $(image_name)-container python manage.py makemigrations
	@docker exec -it $(image_name)-container python manage.py migrate

format:
	@ruff check --fix
	@ruff format

tests:
	@docker exec -it $(image_name)-container coverage run manage.py test

coverage:
	@docker exec -it $(image_name)-container coverage run manage.py test
	@docker exec -it $(image_name)-container coverage report

terminal:
	@docker exec -it $(image_name)-container bash

.PHONY: run
