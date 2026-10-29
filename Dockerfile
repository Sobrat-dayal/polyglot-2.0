FROM python:3.12-slim
WORKDIR /app
COPY backend/pyproject.toml /app/backend/pyproject.toml
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" httpx google-genai pydantic-settings python-dotenv pytest
COPY backend /app/backend
WORKDIR /app/backend
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
