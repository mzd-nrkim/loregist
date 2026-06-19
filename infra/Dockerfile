FROM pgvector/pgvector:pg16

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        postgresql-server-dev-16 \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fSL "https://github.com/pgbigm/pg_bigm/archive/refs/tags/v1.2-20240606.tar.gz" \
         -o /tmp/pg_bigm.tar.gz \
    && mkdir /tmp/pg_bigm \
    && tar -xzf /tmp/pg_bigm.tar.gz --strip-components=1 -C /tmp/pg_bigm \
    && cd /tmp/pg_bigm \
    && make USE_PGXS=1 \
    && make USE_PGXS=1 install \
    && rm -rf /tmp/pg_bigm /tmp/pg_bigm.tar.gz
