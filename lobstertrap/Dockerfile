# Stub — D-1: pull from veeainc/lobstertrap and build the static Go binary.
# Lobster Trap is MIT, single-binary, no Go toolchain required at runtime.
FROM golang:1.22-alpine AS build
WORKDIR /src
RUN apk add --no-cache git make
RUN git clone --depth 1 https://github.com/veeainc/lobstertrap.git . \
    && make build

FROM alpine:3.20
COPY --from=build /src/lobstertrap /usr/local/bin/lobstertrap
EXPOSE 8080
ENV LOBSTERTRAP_POLICY_DIR=/policies
ENV LOBSTERTRAP_AUDIT_LOG=/data/lobstertrap-audit.log
ENTRYPOINT ["/usr/local/bin/lobstertrap"]
CMD ["serve", "--port", "8080", "--policy-dir", "/policies", "--audit-log", "/data/lobstertrap-audit.log"]
