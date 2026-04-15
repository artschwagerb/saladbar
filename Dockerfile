FROM python:3.14-slim

WORKDIR /pkg

# Allow overriding the version for builds without git history
ARG SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0.dev0
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${SETUPTOOLS_SCM_PRETEND_VERSION}

COPY . .

# Install build tools and build the package
RUN pip install --no-cache-dir build twine && \
    python -m build

# Verify the built artifacts
RUN twine check dist/*

# Install the built wheel to verify it's installable
RUN pip install dist/*.whl && \
    python -c "import saladbar; print('saladbar imported successfully')"

# Run tests
RUN DJANGO_SETTINGS_MODULE=tests.settings \
    python -m django test tests --verbosity=2

CMD ["ls", "-la", "dist/"]
