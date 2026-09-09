# --- Build stage ------------------------------------------------------------
FROM node:22-bookworm-slim AS build
WORKDIR /app

COPY package*.json ./
COPY prisma ./prisma
RUN npm ci

COPY . .
RUN npx prisma generate
RUN npm run build

# --- Production stage --------------------------------------------------------
FROM node:22-bookworm-slim AS production
WORKDIR /app
ENV NODE_ENV=production

# Non-root user
RUN groupadd -r nodeapp && useradd -r -g nodeapp nodeapp

COPY package*.json ./
COPY prisma ./prisma
RUN npm ci --omit=dev && npx prisma generate

COPY --from=build /app/dist ./dist

USER nodeapp
EXPOSE 3001

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD node -e "require('http').get('http://127.0.0.1:3001/api/v1/health', r => process.exit(r.statusCode===200?0:1)).on('error', () => process.exit(1))"

CMD ["node", "dist/main.js"]
