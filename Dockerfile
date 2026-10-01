FROM python:3.12-slim
WORKDIR /app
ENV TZ=Asia/Shanghai
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir flask PyPDF2 waitress
COPY scripts/ /app/scripts/
COPY app/ /app/app/
COPY data/ /app/data/
RUN mkdir -p /app/reports
EXPOSE 9090
CMD ["python3", "app/server.py"]
