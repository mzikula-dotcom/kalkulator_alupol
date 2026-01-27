FROM python:3.9-slim

# Instalace systémových závislostí pro Playwright a Chromium
RUN apt-get update && apt-get install -y \
    wget \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Nastavení pracovního adresáře
WORKDIR /app

# Kopírování souborů
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalace Playwright prohlížečů
RUN playwright install chromium
RUN playwright install-deps

COPY . .

# Spuštění Streamlit aplikace
CMD ["streamlit", "run", "app.py", "--server.port=$PORT", "--server.address=0.0.0.0"]
