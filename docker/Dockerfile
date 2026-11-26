# syntax=docker/dockerfile:1
# Flipper One MCU toolchain image: the linux bundle on a pinned Debian.
#
# Build context: a directory holding the linux bundles and their .sha256 files, e.g. dist/:
#   docker buildx build -f docker/Dockerfile --platform linux/amd64,linux/arm64 \
#     --build-arg TOOLCHAIN_TAG=<tag> dist/
#
# ENV mirrors fbtenv.sh; tests/test_env.py checks the two agree.

ARG DEBIAN_IMAGE=debian:trixie-20261104-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
FROM ${DEBIAN_IMAGE}

# Links the ghcr package to its repository (visibility, permissions, README).
LABEL org.opencontainers.image.source=https://github.com/flipperdevices/flipperone-mcu-toolchain \
      org.opencontainers.image.description="Flipper One MCU toolchain" \
      org.opencontainers.image.licenses="MIT AND GPL-3.0-or-later AND GPL-2.0-or-later AND BSD-3-Clause AND Apache-2.0 AND LGPL-2.1-or-later AND LGPL-2.1-only"

ARG DEBIAN_SNAPSHOT=20261104T000000Z
ARG TARGETARCH
ARG TOOLCHAIN_TAG

# Signed snapshot metadata pins every package version; plain http is how snapshot.debian.org
# is reached before ca-certificates is installed, and apt still verifies the signatures.
# libudev1 is the one system library the bundled USB libraries need.
RUN set -eux; \
    rm -f /etc/apt/sources.list.d/*; \
    printf '%s\n' \
      "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}/ trixie main" \
      "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT}/ trixie-security main" \
      > /etc/apt/sources.list; \
    apt-get -o Acquire::Retries=3 update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates git xz-utils libudev1; \
    rm -rf /var/lib/apt/lists/*

RUN --mount=type=bind,source=.,target=/ctx set -eux; \
    test -n "${TOOLCHAIN_TAG}"; \
    case "${TARGETARCH}" in \
      amd64) platform=linux-x86_64 ;; \
      arm64) platform=linux-aarch64 ;; \
      *) echo "unsupported architecture ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    archive="flipperone-mcu-toolchain-${TOOLCHAIN_TAG}-${platform}.tar.gz"; \
    (cd /ctx && sha256sum -c "${archive}.sha256"); \
    mkdir -p /opt/flipperone-mcu-toolchain; \
    tar -xzf "/ctx/${archive}" -C /opt/flipperone-mcu-toolchain; \
    useradd --uid 1000 --create-home builder

ENV FLIPPERONE_TOOLCHAIN=${TOOLCHAIN_TAG} \
    FLIPPERONE_TOOLCHAIN_ROOT=/opt/flipperone-mcu-toolchain \
    PICO_SDK_PATH=/opt/flipperone-mcu-toolchain/pico-sdk \
    PICO_TOOLCHAIN_PATH=/opt/flipperone-mcu-toolchain/tools/arm-none-eabi-gcc \
    picotool_DIR=/opt/flipperone-mcu-toolchain/tools/picotool \
    pioasm_DIR=/opt/flipperone-mcu-toolchain/tools/pioasm \
    OPENOCD_SCRIPTS=/opt/flipperone-mcu-toolchain/tools/openocd/scripts \
    PYTHONNOUSERSITE=1 \
    PATH=/opt/flipperone-mcu-toolchain/tools/arm-none-eabi-gcc/bin:/opt/flipperone-mcu-toolchain/tools/picotool:/opt/flipperone-mcu-toolchain/tools/pioasm:/opt/flipperone-mcu-toolchain/tools/openocd:/opt/flipperone-mcu-toolchain/tools/cmake/bin:/opt/flipperone-mcu-toolchain/tools/ninja/bin:/opt/flipperone-mcu-toolchain/tools/python/bin:/opt/flipperone-mcu-toolchain/tools/uv:/opt/flipperone-mcu-toolchain/tools/ccache:/opt/flipperone-mcu-toolchain/tools/clang-format/bin:/opt/flipperone-mcu-toolchain/tools/clang-tidy/bin:/opt/flipperone-mcu-toolchain/tools/clangd/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

USER builder
WORKDIR /home/builder
