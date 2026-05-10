# D1 stub — minimal HTTP server reading the SQLite ledger.
# Real Next.js + tRPC + better-sqlite3 implementation lands D5 (T6.1+).
FROM node:20-alpine
RUN apk add --no-cache python3 make g++
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev --build-from-source=better-sqlite3
COPY server.js ./
EXPOSE 3000
ENV LEDGER_PATH=/data/diwan.db
ENV PORT=3000
CMD ["node", "server.js"]
