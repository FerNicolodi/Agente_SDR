FROM python:3.12-slim

# HIGH-02: criar usuário sem privilégios — o processo não deve rodar como root
RUN addgroup --system app && adduser --system --ingroup app app

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# HIGH-02: mudar para usuário sem privilégios antes de iniciar o servidor
USER app

EXPOSE 8000

# LOW-01: HEALTHCHECK para que o orquestrador saiba quando o serviço está pronto
# e reinicie o contêiner automaticamente em caso de falha
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" \
    || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
