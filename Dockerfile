FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 创建数据目录
RUN mkdir -p /data

# HF Spaces 要求监听 7860 端口
ENV PORT=7860
EXPOSE 7860

# 使用 gunicorn 启动
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:7860", "--workers", "1", "--preload", "--timeout", "120"]
