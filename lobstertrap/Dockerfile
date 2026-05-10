# D-1: pull from veeainc/lobstertrap and build the static Go binary.
# Lobster Trap is MIT, single-binary, no Go toolchain required at runtime.
#
# Verified upstream (2026-05-09):
#   - Makefile target `build` -> `go build -o lobstertrap .`
#   - Entry point: ./main.go (delegates to ./cmd via cobra)
#   - CLI: `lobstertrap serve --policy <file> --listen <addr> --backend <url> --audit-log <path>`
#   - NO `--policy-dir` flag -- policy is a single YAML file
#   - NO `--port` flag -- use `--listen :8080`
#   - Audit log format: JSONL (one JSON object per line, schema in internal/audit/logger.go)
FROM golang:1.22-alpine AS build
WORKDIR /src
RUN apk add --no-cache git make
RUN git clone --depth 1 https://github.com/veeainc/lobstertrap.git . \
    && make build-static

FROM alpine:3.20
RUN apk add --no-cache ca-certificates
COPY --from=build /src/lobstertrap /usr/local/bin/lobstertrap
EXPOSE 8080
# Default policy + audit paths -- override at `docker run` time if needed.
# Note: --policy takes a FILE, not a directory. Mount /policies and point at a specific file.
ENTRYPOINT ["/usr/local/bin/lobstertrap"]
CMD ["serve", \
     "--policy", "/policies/agent-safety.yaml", \
     "--listen", ":8080", \
     "--audit-log", "/data/lobstertrap-audit.log"]
