.PHONY: build check test clean publish

# Resolve version from git tags in PEP 440 format.
# Tagged commit: v0.2.0 -> 0.2.0
# After tag:     v0.2.0-3-gabcdef -> 0.2.0.dev3
VERSION := $(shell tag=$$(git describe --tags --match 'v*' 2>/dev/null) && \
	echo "$$tag" | sed -E 's/^v//; s/-([0-9]+)-g[0-9a-f]+$$/.dev\1/' \
	|| echo "0.0.0.dev0")

# Build the package in Docker (no local Python needed)
build:
	docker build --build-arg SETUPTOOLS_SCM_PRETEND_VERSION=$(VERSION) -t django-saladbar-build .
	docker run --rm -v $(PWD)/dist:/out django-saladbar-build sh -c "cp dist/* /out/"

# Validate syntax, run tests, and check package metadata in Docker
check:
	docker build --build-arg SETUPTOOLS_SCM_PRETEND_VERSION=$(VERSION) -t django-saladbar-build .

# Run tests only
test:
	docker build --build-arg SETUPTOOLS_SCM_PRETEND_VERSION=$(VERSION) -t django-saladbar-build .
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
