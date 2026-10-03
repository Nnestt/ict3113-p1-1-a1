# Build context is service/ (see docker-compose.yml). classifier.py, eval_config.json and prompt_template.md
# are unchanged copies of the frozen files in evaluation/.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY classifier.py eval_config.json prompt_template.md app.py storage.py request_log.py ./
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
