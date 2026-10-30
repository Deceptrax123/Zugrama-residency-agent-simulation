FROM python:3.12-slim
WORKDIR /app
RUN useradd --uid 10001 --create-home resident && mkdir /app/.data && chown resident:resident /app/.data
COPY --chown=resident:resident residency /app/residency
COPY --chown=resident:resident USER.md /app/USER.md
USER resident
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 7340
CMD ["python", "-B", "-m", "residency.server", "--host", "0.0.0.0", "--port", "7340"]
