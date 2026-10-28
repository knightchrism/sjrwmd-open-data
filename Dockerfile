# Harvester image: python harvest.py [--only ALIAS ...]
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY harvest.py layers.yaml esri_inventory.csv ./
USER 10001
ENTRYPOINT ["python", "harvest.py"]
