FROM ubuntu:24.04

# Prevent interactive prompts during installation
ARG DEBIAN_FRONTEND=noninteractive

# Update & install essential packages:
#   software-properties-common: for add-apt-repository
#   curl, jq: for requesting Gmail access token
#   ca-certificates: for HTTPS requests (Gmail API, pip installs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    curl \
    jq \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Add deadsnakes PPA and install Python3.11
RUN add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3.11-distutils \
    && rm -rf /var/lib/apt/lists/*

# Setup Python and pip
RUN <<EOF
curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1
python3 --version
EOF

# Set working directory
WORKDIR /app

# Copy dependency file and source code first
COPY ./requirements.txt ./src ./pyproject.toml ./README.md ./

# Install Python dependencies and chromium headless shell as root
RUN <<EOF
python3 -m pip install --no-cache-dir --upgrade --root-user-action ignore pip
python3 -m pip install --no-cache-dir --root-user-action ignore -r requirements.txt
python3 -m playwright install --with-deps --only-shell chromium
python3 -m pip install --no-cache-dir --root-user-action ignore .
EOF

# Add .local/bin to PATH
# ENV PATH="/root/.local/bin:$PATH"

# Copy other files
COPY . .

# Make entrypoint executable (for non-root user, may need to do it on host)
RUN chmod +x ./docker/docker-entrypoint.sh

ENTRYPOINT ["/app/docker/docker-entrypoint.sh"]
