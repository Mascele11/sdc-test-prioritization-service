FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy config source
COPY config/ ./config/
COPY src/    ./src/
COPY main.py .

# Create logs directory
RUN mkdir -p logs

ENV PYTHONPATH="/app/src"

ENTRYPOINT ["python", "main.py"]
