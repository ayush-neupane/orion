# ============================================================
# ORION frontend image: build (with npm audit gate) -> nginx
# ============================================================
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund || npm install --no-fund

FROM build AS audit
COPY . .
RUN npm audit --audit-level=critical \
    || (echo "SECURITY AUDIT FAILED: critical npm vulnerabilities" && exit 1)

FROM node:22-alpine AS tester
WORKDIR /app
COPY --from=build /app/node_modules ./node_modules
COPY . .
RUN npm run typecheck && npx vite build

FROM nginx:1.27-alpine AS runtime
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/orion.conf
COPY --from=tester /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget -qO- http://localhost/ >/dev/null 2>&1 || exit 1
CMD ["nginx", "-g", "daemon off;"]
