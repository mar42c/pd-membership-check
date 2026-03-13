FROM python:3.12-slim

# Install system deps if needed (curl for debugging etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
 && rm -rf /var/lib/apt/lists/*

# Set workdir
WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY app.py .

# Environment (optional)
ENV PYTHONUNBUFFERED=1

# Expose Flask/Gunicorn port
EXPOSE 5000

# Run with Gunicorn (4 workers, listening on 0.0.0.0:5000)
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]