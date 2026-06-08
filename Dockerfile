# Use the official Python 3.11 slim image
FROM python:3.11-slim

# Install system dependencies needed to compile python packages (like pycairo)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    pkg-config \
    libcairo2-dev \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user (required by Hugging Face Spaces and best practice for security)
RUN useradd -m -u 1000 user
WORKDIR /home/user/app

# Copy requirements first to leverage Docker cache
COPY --chown=user:user requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser and its exact system dependencies automatically
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy the rest of the application files
COPY --chown=user:user . .

# Use the pre-seeded database as the active database
RUN cp seed_database.sqlite lab_database.db

# Ensure directory permissions are correct for temporary files and uploads
RUN mkdir -p tmp uploads/attachments uploads/chat_media backups && \
    chown -R user:user /home/user/app

# Switch to the non-root user
USER user

# Set environment variables
ENV PORT=7860
ENV DATABASE_URL=sqlite:///./lab_database.db
ENV PYTHONUNBUFFERED=1

# Expose the port (Hugging Face Spaces uses 7860 by default)
EXPOSE 7860

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
