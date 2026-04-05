.PHONY: build check test clean publish

# Build the package in Docker (no local Python needed)
build:
	docker build -t django-saladbar-build .
	docker run --rm -v $(PWD)/dist:/out django-saladbar-build sh -c "cp dist/* /out/"

# Validate syntax, run tests, and check package metadata in Docker
check:
	docker build -t django-saladbar-build .

# Run tests only
test:
	docker build -t django-saladbar-build .
	docker run --rm django-saladbar-build \
		sh -c "DJANGO_SETTINGS_MODULE=tests.settings python -m django test tests --verbosity=2"

# Remove build artifacts
clean:
	rm -rf dist/ build/ src/*.egg-info

# Publish to PyPI (requires TWINE_USERNAME and TWINE_PASSWORD env vars)
publish: build
	docker run --rm \
		-e TWINE_USERNAME \
		-e TWINE_PASSWORD \
		-v $(PWD)/dist:/pkg/dist \
		django-saladbar-build \
		twine upload dist/*
