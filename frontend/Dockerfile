# NarratIQ frontend image (Stage 10, task 10.3).
#
# Builds the same Next.js app start-narratiq.sh builds, with the same two
# build-time settings (Stage 10, 10.7):
#   BACKEND_INTERNAL_URL  where the Next.js server forwards /api/* (same-origin
#                         API; the session cookie stays first-party)
#   NEXT_PUBLIC_API_URL   the backend's browser-reachable URL, used ONLY for the
#                         voice WebSocket
# Both are inlined at build time, so they are build arguments, not runtime env.
#
# Versions pinned: node 20.20.2 (the pod's version), dependencies from
# package-lock.json via `npm ci`. Base-image digest: see docs/operations/containers.md.
FROM node:20.20.2-bookworm-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG BACKEND_INTERNAL_URL=http://backend:8000
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV BACKEND_INTERNAL_URL=${BACKEND_INTERNAL_URL} \
    NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
RUN npm run build && npm prune --omit=dev

FROM node:20.20.2-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=build --chown=node:node /app/package.json /app/package-lock.json /app/next.config.js ./
COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/.next ./.next
USER node
EXPOSE 3000
CMD ["npx", "next", "start", "-p", "3000"]
