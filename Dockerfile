FROM python:3.14-slim

WORKDIR /pkg

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
