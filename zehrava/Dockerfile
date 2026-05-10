# Stub — D-1: build Zehrava Gate Node service from vendored packages/.
FROM node:20-alpine
WORKDIR /app
COPY packages/ ./packages/
COPY policies/ ./policies/
COPY schemas/ ./schemas/
RUN cd packages/server && npm ci --omit=dev || npm install --omit=dev
EXPOSE 4000
ENV ZEHRAVA_POLICY_DIR=/policies
ENV ZEHRAVA_LEDGER_PATH=/data/diwan.db
CMD ["node", "packages/server/index.js"]
