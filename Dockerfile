FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt pyproject.toml README.md ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "super_trader_quant.backend.app.main:app", "--host", "0.0.0.0", "--port", "8010"]
