FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV BISNU_HOST=0.0.0.0
ENV BISNU_PORT=8080

EXPOSE 8080

CMD ["python", "run_web.py"]
