# ─── Stage 1: Build Mastra Agents ─────────────────────────────────────────────
FROM node:20-bookworm AS builder

WORKDIR /app

COPY mastra-agents/package*.json ./
RUN npm ci --production=false

COPY mastra-agents/ ./
RUN npm run build

# ─── Stage 2: Build Remotion Renderer ─────────────────────────────────────────
FROM node:20-bookworm AS remotion-builder

WORKDIR /renderer

COPY remotion-renderer/package*.json ./
RUN npm ci

COPY remotion-renderer/ ./

# ─── Stage 3: Runtime ─────────────────────────────────────────────────────────
FROM node:20-bookworm-slim

# System dependencies for Chromium (required by Remotion's headless shell)
RUN apt-get update && apt-get install -y --no-install-recommends \
  libnss3 \
  libatk1.0-0 \
  libatk-bridge2.0-0 \
  libcups2 \
  libdrm2 \
  libxkbcommon0 \
  libxcomposite1 \
  libxdamage1 \
  libxrandr2 \
  libgbm1 \
  libpango-1.0-0 \
  libcairo2 \
  libasound2 \
  libxshmfence1 \
  ffmpeg \
  wget \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Mastra agents build
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json

# Copy Remotion renderer (full source + node_modules — needed for npx remotion render)
COPY --from=remotion-builder /renderer ./remotion-renderer

# Install Chrome Headless Shell for Remotion
RUN npx @remotion/install-chrome-headless-shell 2>/dev/null || true

# Create data directories
RUN mkdir -p /data/videos /data/panels /data/music /data/logs

# Non-root user for security
RUN groupadd -r manga && useradd -r -g manga manga
RUN chown -R manga:manga /app /data
USER manga

EXPOSE 3001

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD wget -qO- http://localhost:3001/health || exit 1

CMD ["node", "dist/server.js"]
