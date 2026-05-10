# Stub — D-2: toy CRM agent. 4 tools: web.fetch, db.write, mail.send, api.post.
FROM node:20-alpine
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY src/ ./src/
ENV OPENAI_BASE_URL=http://lobstertrap:8080/v1
ENV ZEHRAVA_URL=http://zehrava:4000
CMD ["node", "src/index.js"]
