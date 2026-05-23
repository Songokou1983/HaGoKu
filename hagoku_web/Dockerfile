# HaGoKu Studio — Web 前端开发 Docker 镜像
FROM node:20-alpine

WORKDIR /app

# 复制依赖文件
COPY package.json package-lock.json ./
RUN npm ci

# 复制应用代码（运行时通过 volume 覆盖实现热加载）
COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]