# CDR Frontend - React (Vite) built and served via nginx

# ---- Build stage ----
FROM node:20-alpine AS build
WORKDIR /app

# Relative /api path so nginx (below) can proxy requests to the backend container.
# Override at build time with --build-arg VITE_API_URL=... if serving differently.
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL

COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# ---- Serve stage ----
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
