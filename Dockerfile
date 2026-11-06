# 四史学习助手 —— 服务端镜像
# 构建：docker build -t ss-helper .
# 运行：docker compose up -d（见 docker-compose.yml，数据落在 ./data 卷里）
FROM python:3.11-slim

WORKDIR /app

# 先装依赖（这层缓存最稳定），再拷代码
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend
# 前端构建产物由 CI/构建者先跑好：frontend/dist → /app/frontend_dist（apppaths 的默认查找位置）
COPY frontend/dist frontend/dist

ENV APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    PYTHONUNBUFFERED=1

EXPOSE 8000
VOLUME ["/app/data"]

# 数据库/上传文件/.env 都在 /app/data 下，挂卷即持久化
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "backend"]
