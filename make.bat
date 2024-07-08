@echo off

SET image_name=intel_middleware

IF /I "%1"=="setup" GOTO setup
IF /I "%1"=="docs" GOTO docs
IF /I "%1"=="run-local" GOTO run-local
IF /I "%1"=="build" GOTO build
IF /I "%1"=="run" GOTO run
IF /I "%1"=="run-detached" GOTO run-detached
IF /I "%1"=="stop" GOTO stop
IF /I "%1"=="migrations" GOTO migrations
IF /I "%1"=="format" GOTO format
IF /I "%1"=="tests" GOTO tests
IF /I "%1"=="coverage" GOTO coverage
IF /I "%1"=="terminal" GOTO terminal
GOTO error

:setup
	@python -m venv venv
	@source venv/bin/activate
	@pip install --upgrade pip
	@pip install -r requirements.txt
	@pip install pre-commit
	@pre-commit install
	@copy .env.template .env
	GOTO :EOF

:docs
	@docker exec -it %image_name%-container python manage.py spectacular --color --file schema.yml
	GOTO :EOF

:run-local
	@python manage.py runserver
	GOTO :EOF

:build
	@docker build --tag %image_name% .
	@docker image prune -f
	GOTO :EOF

:run
	@docker run -v "%cd%":/app --rm -it -p 8000:8000 --name %image_name%-container %image_name%
	GOTO :EOF

:run-detached
	@docker run -v "%cd%":/app --rm -it -p 8000:8000 -d --name %image_name%-container %image_name%
	GOTO :EOF

:stop
	@docker stop %image_name%-container
	GOTO :EOF

:migrations
	@docker exec -it %image_name%-container python manage.py makemigrations
	@docker exec -it %image_name%-container python manage.py migrate
	GOTO :EOF

:format
	@ruff check --fix
	@ruff format
	GOTO :EOF

:tests
	@docker exec -it %image_name%-container coverage run manage.py test
	GOTO :EOF

:coverage
	@docker exec -it %image_name%-container coverage run manage.py test
	@docker exec -it %image_name%-container coverage report
	GOTO :EOF

:terminal
	@docker exec -it %image_name%-container bash
	GOTO :EOF

:error
    IF "%1"=="" (
        ECHO make: *** No targets specified and no makefile found.  Stop.
    ) ELSE (
        ECHO make: *** No rule to make target '%1%'. Stop.
    )
    GOTO :EOF
