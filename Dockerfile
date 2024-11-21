# Debian 11 is recommended.
FROM python:3.12-slim

# Suppress interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# (Required) Install utilities required by Spark scripts.
RUN apt update && apt install -y procps tini libjemalloc2 && \
rm -rf /var/lib/apt/lists/*

# Enable jemalloc2 as default memory allocator
ENV LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2

ENV PYSPARK_PYTHON=/usr/local/bin/python3

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# (Required) Create the 'spark' group/user.
# The GID and UID must be 1099. Home directory is required.
RUN groupadd -g 1099 spark
RUN useradd -u 1099 -g 1099 -d /home/spark -m spark
USER spark