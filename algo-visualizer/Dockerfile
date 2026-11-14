# syntax=docker/dockerfile:1
# ---------- Stage 1: run the test suite inside the build ----------
FROM node:22-alpine AS test
WORKDIR /app
COPY package.json ./
COPY src ./src
COPY public ./public
COPY test ./test
RUN npm test && node --check public/app.js

# ---------- Stage 2: minimal runtime image ----------
FROM node:22-alpine AS runtime
ARG APP_VERSION=dev
ENV NODE_ENV=production \
    PORT=8080 \
    APP_VERSION=${APP_VERSION}
WORKDIR /app
# Copying from the test stage guarantees the image is only produced if tests pass.
COPY --from=test --chown=node:node /app/package.json ./
COPY --from=test --chown=node:node /app/src ./src
COPY --from=test --chown=node:node /app/public ./public
USER node
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1
# exec form -> node is PID 1 and receives SIGTERM directly (graceful shutdown)
CMD ["node", "src/server.js"]
