FROM python:3.12.1-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app_distribution_server.app:app", "--host", "0.0.0.0", "--port", "8000"] 