FROM node:24-alpine AS dependencies
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@10.33.0 --activate
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY frontend/package.json frontend/package.json
RUN pnpm install --frozen-lockfile
COPY frontend/ frontend/
FROM dependencies AS development
RUN chown -R node:node /app
USER node
EXPOSE 8080
CMD ["pnpm", "--dir", "frontend", "dev", "--host", "0.0.0.0", "--port", "8080"]

FROM dependencies AS build
RUN pnpm --dir frontend build

FROM nginxinc/nginx-unprivileged:alpine
COPY infra/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html
EXPOSE 8080
