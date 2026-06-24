# Deployment

The server Dockerfile uses a Node stage to build the dashboard and a Python
stage to install and run the Goodomics server.

## Build the server image

```bash
docker build -f docker/Dockerfile.server -t goodomics/server:local .
```

## Run the server

```bash
goodomics serve --host 0.0.0.0 --port 8000
```

## Package build with dashboard assets

Use the repository script when Python packages should include the built
dashboard assets:

```bash
scripts/build-python-packages.sh
```

!!! warning "Generated dashboard assets"
    Dashboard build output under `goodomics/server/web/static` is generated and
    ignored by git. Build it for verification or packaging, but do not commit
    hashed static assets.
