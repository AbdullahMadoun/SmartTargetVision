ARG PX4_GAZEBO_IMAGE=px4io/px4-sitl-gazebo@sha256:e5616cc4b6c4e89021f6052d6b721147cdadc4eafab778d98a1a7ff6b4ec06fb
FROM ${PX4_GAZEBO_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:0
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=graphics,utility,compute

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    libopencv-core406t64 \
    libopencv-imgproc406t64 \
    libopencv-video406t64 \
    libgstreamer1.0-0 \
    libgstreamer-plugins-base1.0-0 \
    eterm \
    fluxbox \
    novnc \
    websockify \
    procps \
    x11-utils \
    x11-apps \
    x11-xserver-utils \
    xdotool \
    mesa-utils \
    libegl1-mesa \
    libgl1-mesa-glx \
    libglu1-mesa \
    && wget -q "https://packagecloud.io/dcommander/virtualgl/packages/any/any/virtualgl_3.1.4-20251008_amd64.deb/download.deb" -O /tmp/vgl.deb \
    && wget -q "https://github.com/TurboVNC/turbovnc/releases/download/3.3/turbovnc_3.3_amd64.deb" -O /tmp/tvnc.deb \
    && apt-get install -y /tmp/vgl.deb /tmp/tvnc.deb \
    && rm -f /tmp/vgl.deb /tmp/tvnc.deb \
    && rm -rf /var/lib/apt/lists/*

COPY docker/visual-entrypoint.sh /usr/local/bin/visual-entrypoint.sh
RUN chmod +x /usr/local/bin/visual-entrypoint.sh

EXPOSE 5900 6080 14540/udp 14550/udp 8888/udp
ENTRYPOINT ["/usr/local/bin/visual-entrypoint.sh"]
