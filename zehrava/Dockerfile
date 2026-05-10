# Stub — D-1: build Zehrava Gate Node service from vendored packages/.
FROM node:20-alpine
WORKDIR /app
COPY packages/ ./packages/
COPY policies/ ./policies/
COPY schemas/ ./schemas/
RUN cd packages/gate-server && (npm ci --omit=dev --legacy-peer-deps || npm install --omit=dev --legacy-peer-deps)
EXPOSE 4000
ENV PORT=4000
ENV ZEHRAVA_POLICY_DIR=/policies
ENV ZEHRAVA_LEDGER_PATH=/data/diwan.db
CMD ["node", "packages/gate-server/src/index.js"]
