FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
COPY apps/api/package.json apps/api/package.json
COPY packages packages
RUN npm install

FROM deps AS build
COPY apps/api apps/api
COPY tsconfig.base.json ./
RUN npm run build --workspace @shuddho/api

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app /app
EXPOSE 4000
CMD ["npm", "run", "start", "--workspace", "@shuddho/api"]
