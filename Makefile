.PHONY: lint

lint:
	isort .
	black . --line-length 120
	flake8 . --ignore=E501,W503,E203,E402,W605
	mypy . --ignore-missing-imports
