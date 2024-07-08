# syntax=docker/dockerfile:1.4

FROM python:3.11

WORKDIR /app
COPY . .
EXPOSE 8000

RUN pip3 install --upgrade pip
RUN pip3 install -r requirements.txt --no-cache-dir

ENTRYPOINT ["python3"]
CMD ["manage.py", "runserver", "0.0.0.0:8000"]