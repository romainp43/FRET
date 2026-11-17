# Image minimale, non-root. Aucune dépendance Python externe (bibliothèque standard uniquement).
FROM python:3.15-slim
RUN useradd --system --uid 10001 --no-create-home fretrau && mkdir /data && chown fretrau /data
WORKDIR /app
COPY --chown=root:root . /app
USER fretrau
ENV HOST=0.0.0.0 PORT=8080 FRETRAU_DB=/data/fretrau.db FRETRAU_PLACES_DB=/data/places.db FRETRAU_HTTPS=1 FRETRAU_TRUST_PROXY=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python3 -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/legal/cookies.html')"
CMD ["sh", "deploy/start.sh"]
