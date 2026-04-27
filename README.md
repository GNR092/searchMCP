# searchmcp

Servidor MCP de búsqueda híbrida multilingüe (español + inglés) con caché local, ChromaDB persistente y DuckDuckGo.

## Requisitos

- Python >= 3.9
- `codesearch` (opcional, para indexado automático del historial)

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
Búsqueda local primero
  ├── Literal en .search/
  └── Semántica en ChromaDB
    │
    ▼
Fusión + deduplicación + reranking
    │
    ▼
¿Score >= 0.60?
  ├── Sí: responde local (sin web)
  └── No: DuckDuckGo fallback
          + guardar en .search/
          + indexar en ChromaDB
```

## Modelo de Embeddings

- Modelo: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- Base vectorial: ChromaDB persistente en `.search/chroma/`
- Dispositivo: CPU por defecto, CUDA automático si está disponible

## Parámetros de Búsqueda

- `default_top_k = 5`
- `max_top_k = 10`
- `similarity_threshold = 0.60`

## Herramientas MCP

### `search`

Búsqueda web directa en DuckDuckGo (sin híbrido).

**Argumentos:**
- `query` (string, requerido)
- `max_results` (integer, opcional, default: 10)

### `search_cached` (recomendada)

Búsqueda híbrida local+semántica con fallback web solo si no hay resultados útiles.

**Argumentos:**
- `query` (string, requerido)
- `top_k` (integer, opcional, default: 5, max: 10)
- `similarity_threshold` (float, opcional, default: 0.60)
- `web_max_results` (integer, opcional, default: 10, max: 10)
- `auto_index` (boolean, opcional, default: true)

### `search_and_save`

Fuerza búsqueda web, guarda en `.search/history/` e indexa.

**Argumentos:**
- `query` (string, requerido)
- `max_results` (integer, opcional, default: 10)
- `auto_index` (boolean, opcional, default: true)

### `search_cleanup`

Elimina historial de más de 30 días (solo `history`, no `cache`, no `chroma`).

### `search_stats`

Muestra estado de caché, historial, codesearch, ChromaDB, modelo y dispositivo.

## Estructura de Datos

```text
.search/
├── cache/        # caché permanente de queries
├── history/      # historial con TTL de 30 días
└── chroma/       # ChromaDB persistente
```

## Metadatos guardados por resultado

- `query_original`
- `idioma_detectado`
- `titulo`
- `url`
- `dominio`
- `fuente` (`cache`, `chroma`, `duckduckgo`)
- `fecha_indexacion`
- `fecha_acceso`
- `access_count`
- `hash_contenido`
- `hash_url`
- `fragmento_normalizado`
- `score` (normalizado 0-1)
