FROM node:24-alpine@sha256:a0b9bf06e4e6193cf7a0f58816cc935ff8c2a908f81e6f1a95432d679c54fbfd AS deps
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json ./
COPY apps/api/package.json apps/api/package.json
COPY packages/shared/package.json packages/shared/package.json
RUN pnpm install --frozen-lockfile

FROM deps AS build
COPY apps apps
COPY packages packages
COPY prisma prisma
COPY scripts scripts
RUN pnpm db:generate && pnpm build

FROM node:24-alpine@sha256:a0b9bf06e4e6193cf7a0f58816cc935ff8c2a908f81e6f1a95432d679c54fbfd AS runtime
WORKDIR /app
ENV NODE_ENV=production
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/api/package.json apps/api/package.json
COPY packages/shared/package.json packages/shared/package.json
COPY --from=build /app/prisma prisma
RUN pnpm install --prod --frozen-lockfile
COPY --from=build /app/apps/api/dist apps/api/dist
COPY --from=build /app/packages/shared/dist packages/shared/dist
COPY --from=build /app/scripts scripts
RUN rm -rf \
    /app/package.json \
    /app/pnpm-lock.yaml \
    /app/pnpm-workspace.yaml \
    /root/.cache/node/corepack \
    /root/.local/share/pnpm \
    /root/.pnpm-store \
    /usr/local/bin/corepack \
    /usr/local/bin/npm \
    /usr/local/bin/npx \
    /usr/local/bin/pnpm \
    /usr/local/bin/pnpx \
    /usr/local/lib/node_modules/corepack \
    /usr/local/lib/node_modules/npm \
  && addgroup -S app && adduser -S app -G app \
  && mkdir -p /app/data/uploads \
  && chown -R app:app /app
USER app
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD wget -qO- http://127.0.0.1:3000/actuator/health || exit 1
CMD ["node", "apps/api/dist/main.js"]
