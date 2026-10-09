FROM python:3.12-slim
COPY app /app/app
RUN touch /app/app/__init__.py && python3 -m compileall -q /app
WORKDIR /app
ENV PYTHONUNBUFFERED=1
CMD ["python3", "-m", "app.daemon"]
