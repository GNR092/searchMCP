# searchmcp

Servidor MCP de búsqueda semántica multilingüe (español + inglés) con embeddings locales, ChromaDB persistente y DuckDuckGo.

## Requisitos

- Python >= 3.10
- `sentence-transformers` (para embeddings E5 y reranker opcional)
- `chromadb` (para índice semántico persistente)
- `ddgs` / `duckduckgo-search` (búsqueda web)

## Instalación

```bash
pip install -r requirements.txt
pip install -e .
```

## Uso

```bash
python -m searchmcp.server
```

## Arquitectura

```text
Consulta usuario
    │
    ▼
Normalización
    │
    ▼
Búsqueda semántica en ChromaDB (E5 + query:)
    │
    ▼
¿Score >= 0.60?
  ├── Sí: re-rankear y responder local (sin web)
  └── No: DuckDuckGo fallback
          + guardar historial en .search/history/
          + indexar en ChromaDB (E5 + passage:)
          + re-rankear resultados combinados
```

## Modelo de Embeddings

- Modelo de embeddings: `intfloat/multilingual-e5-small` (en+es, 384d)
  - Consultas indexadas con prefijo `query:`
  - Documentos indexados con prefijo `passage:`
  - Truncamiento automático a 512 tokens
- Reranker opcional: `cross-encoder/ms-marco-MiniLM-L-6-v2`
  - Desactivar: `SEARCHMCP_DISABLE_RERANKER=1`
  - Cambiar modelo: `SEARCHMCP_RERANKER_MODEL=...`
- Caché LRU de embeddings (consultas y documentos) en memoria
- Base vectorial: ChromaDB persistente en `.search/chroma/`
- Dispositivo: CPU por defecto, CUDA automático si está disponible
- Forzar modo web sin embeddings: `SEARCHMCP_DISABLE_EMBEDDINGS=1`

## Parámetros de Búsqueda

- `default_top_k = 5`
- `max_top_k = 10`
- `similarity_threshold = 0.60`
- `SEARCHMCP_EMBEDDING_BATCH_SIZE = 32` (tamaño de batch al indexar documentos)

## Herramientas MCP

### `search`

Búsqueda web directa en DuckDuckGo (sin híbrido).

**Argumentos:**
- `query` (string, requerido)
- `max_results` (integer, opcional, default: 10)

### `search_cached` (recomendada)

Búsqueda semántica en ChromaDB con re-ranking y fallback a DuckDuckGo si no hay resultados locales útiles.

**Argumentos:**
- `query` (string, requerido)
- `top_k` (integer, opcional, default: 5, max: 10)
- `similarity_threshold` (float, opcional, default: 0.60)
- `web_max_results` (integer, opcional, default: 10, max: 10)

### `search_and_save`

Fuerza búsqueda web, guarda el historial en `.search/history/` y embebe los resultados en ChromaDB.

**Argumentos:**
- `query` (string, requerido)
- `max_results` (integer, opcional, default: 10)

### `search_cleanup`

Elimina historial de más de 30 días (`history`).

### `search_stats`

Muestra estado del historial, ChromaDB, modelo y dispositivo.

## Estructura de Datos

```text
.search/
├── history/      # historial con TTL de 30 días
└── chroma/       # ChromaDB persistente
```

## Variables de entorno

| Variable | Descripción | Default |
|---|---|---|
| `SEARCHMCP_DISABLE_EMBEDDINGS` | `1` para forzar búsqueda web sin cargar embeddings | `0` |
| `SEARCHMCP_DISABLE_RERANKER` | `1` para desactivar el reranker | `0` |
| `SEARCHMCP_RERANKER_MODEL` | Modelo cross-encoder para re-ranking | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| `SEARCHMCP_EMBEDDING_BATCH_SIZE` | Batch size al indexar documentos | `32` |

## Metadatos guardados por resultado

- `query_original`
- `idioma_detectado`
- `titulo`
- `url`
- `dominio`
- `fuente` (`chroma`, `duckduckgo`, `cache+chroma`, con posible sufijo `+rerank`)
- `fecha_indexacion`
- `fecha_acceso`
- `access_count`
- `hash_contenido`
- `hash_url`
- `fragmento_normalizado`
- `score` (normalizado 0-1)
