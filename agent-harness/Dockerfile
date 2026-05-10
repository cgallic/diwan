# D1: toy CRM agent. 4 tools: web.fetch, db.write, mail.send, api.post.
FROM node:20-alpine
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY src/ ./src/
COPY fixtures/ ./fixtures/
ENV OPENAI_BASE_URL=http://lobstertrap:8080/v1
ENV ZEHRAVA_URL=http://zehrava:4000
# ENTRYPOINT so `docker compose run agent-harness "<prompt>"` passes the prompt as argv.
ENTRYPOINT ["node", "src/index.js"]
