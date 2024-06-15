.PHONY: lint

lint:
	isort .
	black . --line-length 120
	flake8 . --ignore=E501,W503,E203
	mypy . --ignore-missing-imports
