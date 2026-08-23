FROM node:20-slim

ENV NODE_ENV=development
WORKDIR /app

COPY package.json ./
RUN npm install

COPY tsconfig.json vite.config.ts index.html .eslintrc.cjs .prettierrc ./
COPY src ./src

EXPOSE 5173
CMD ["npm", "run", "dev"]
