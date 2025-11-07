FROM python:3.12

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY .env .env

# Create necessary directories
RUN mkdir -p data logs

# Run the bot
CMD ["python", "src/main.py"]
