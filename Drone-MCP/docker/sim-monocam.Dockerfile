ARG PX4_GAZEBO_IMAGE=px4io/px4-sitl-gazebo@sha256:e5616cc4b6c4e89021f6052d6b721147cdadc4eafab778d98a1a7ff6b4ec06fb
FROM ${PX4_GAZEBO_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    libopencv-core406t64 \
    libopencv-imgproc406t64 \
    libopencv-video406t64 \
    libgstreamer1.0-0 \
    libgstreamer-plugins-base1.0-0 \
    && rm -rf /var/lib/apt/lists/*
