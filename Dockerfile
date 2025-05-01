FROM python:3.10-slim

WORKDIR /app
COPY . /app

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# No need to copy or set GOOGLE_APPLICATION_CREDENTIALS
CMD ["gunicorn", "--bind", ":8080", "app:app"]
