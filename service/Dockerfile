# Build context is the repo root (see docker-compose.yml) so the frozen classifier is reused, not copied into service/.
FROM python:3.12-slim
WORKDIR /app
COPY service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY evaluation/classifier.py evaluation/eval_config.json evaluation/prompt_template.md ./
COPY service/app.py service/storage.py service/request_log.py ./
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
