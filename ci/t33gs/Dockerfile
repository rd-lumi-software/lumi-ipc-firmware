# The locally provisioned musl cross-compiler requires GLIBC_2.38.
FROM ubuntu:24.04@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852
ENV DEBIAN_FRONTEND=noninteractive LC_ALL=C.UTF-8
RUN apt-get update && apt-get install -y --no-install-recommends \
    autoconf automake bc binutils bison build-essential bzip2 ca-certificates \
    cmake cpio curl file flex gawk git kmod libncurses-dev libssl-dev libtool \
    lzop ninja-build p7zip-full patch perl pkg-config python3 python3-pyelftools \
    ripgrep rsync squashfs-tools tar u-boot-tools unzip wget xz-utils \
    && rm -rf /var/lib/apt/lists/*
ARG RUST_NIGHTLY=nightly-2026-07-20
ENV RUSTUP_HOME=/opt/rustup CARGO_HOME=/opt/cargo PATH=/opt/cargo/bin:$PATH
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs -o /tmp/rustup.sh \
    && sh /tmp/rustup.sh -y --profile minimal --default-toolchain 1.97.1 \
    && rustup toolchain install "$RUST_NIGHTLY" --profile minimal --component rust-src \
    && chmod -R a+rwX /opt/cargo /opt/rustup && rm /tmp/rustup.sh
# Streamer scripts use +nightly; resolve it to the dated installation, offline.
# rustup toolchain link rejects channel names such as "nightly".
RUN ln -s "${RUST_NIGHTLY}-x86_64-unknown-linux-gnu" \
    /opt/rustup/toolchains/nightly-x86_64-unknown-linux-gnu \
    && cargo +nightly --version
WORKDIR /work
