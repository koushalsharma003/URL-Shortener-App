# Use an official Python runtime as a parent image
FROM python:3.9-slim-buster

# Set the working directory in the container
WORKDIR /app

# Install any needed packages specified in requirements.txt
# Copy only requirements.txt first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the port the app runs on
EXPOSE 5000

# Run the application using Gunicorn for production-ready deployment
# -w: number of worker processes (adjust based on CPU cores, typically 2*CPU + 1)
# -b: bind address and port
# app:app refers to 'app' module (app.py) and 'app' Flask instance
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]

