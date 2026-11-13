# Upstream no longer publishes the requested full-console image. Build its
# pinned release source; keep the archive checksum so it cannot drift silently.
FROM golang:1.24-bookworm AS build
ENV CGO_ENABLED=0 GOMAXPROCS=4 GOFLAGS=-p=4
ADD https://codeload.github.com/minio/minio/tar.gz/refs/tags/RELEASE.2025-04-22T22-12-26Z /tmp/minio.tar.gz
RUN echo '1a63209927b9d1fb239b2a776b7b01d1902eff19379a108f4bc7005edcc0968c  /tmp/minio.tar.gz' | sha256sum -c - \
    && mkdir /src \
    && tar -xzf /tmp/minio.tar.gz --strip-components=1 -C /src
WORKDIR /src
RUN go build -trimpath -ldflags='-s -w -X github.com/minio/minio/cmd.Version=2025-04-22T22:12:26Z -X github.com/minio/minio/cmd.ReleaseTag=RELEASE.2025-04-22T22-12-26Z' -o /out/minio .

FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home minio \
    && mkdir /data \
    && chown minio:minio /data
COPY --from=build /out/minio /usr/local/bin/minio
COPY --from=build /src/LICENSE /usr/share/licenses/minio/LICENSE
LABEL org.opencontainers.image.source="https://github.com/minio/minio" \
      org.opencontainers.image.version="RELEASE.2025-04-22T22-12-26Z" \
      org.opencontainers.image.licenses="AGPL-3.0-only"
USER minio
EXPOSE 9000 9001
ENTRYPOINT ["minio"]
CMD ["server", "/data", "--console-address", ":9001"]
