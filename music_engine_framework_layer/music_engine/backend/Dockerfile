FROM python:3.12-slim
WORKDIR /app

# routellm (requirements-routellm.txt) pulls in torch/transformers/scikit-learn —
# this is the only Pecova image that needs them; keep it isolated from
# Akanade's own images rather than adding this weight there. Build with
# --build-arg WITH_ROUTELLM=0 for the slim image (just /route, the deterministic default).
ARG WITH_ROUTELLM=1
COPY requirements.txt requirements-routellm.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
 && if [ "$WITH_ROUTELLM" = "1" ]; then pip install --no-cache-dir -r requirements-routellm.txt; fi

COPY app ./app

EXPOSE 8200
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]
