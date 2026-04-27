# searchmcp

Servidor MCP para búsqueda web con caché permanente usando DuckDuckGo.

## Instalación

```bash
pip install -e .
```

## Uso

```bash
python -m searchmcp.server
```

## Herramientas

### search

Búsqueda web básica sin caché.

**Argumentos:**
- `query` (string, requerido): Término de búsqueda
- `max_results` (integer, opcional): Número máximo de resultados. Default: 10

### search_cached (Recomendado)

Búsqueda con caché permanente. Si la query ya fue buscada, retorna resultados en caché (0 tokens).

**Argumentos:**
- `query` (string, requerido): Término de búsqueda
- `max_results` (integer, opcional): Número máximo de resultados. Default: 10

**Retorna:**
- `[CACHÉ]` si los resultados vienen de caché
- `[NUEVO]` si los resultados son frescos
- Advertencia si caché > 100 entradas

### search_and_save

Busca y guarda en `.search/history/` para integración con codesearch.

**Argumentos:**
- `query` (string, requerido): Término de búsqueda
- `max_results` (integer, opcional): Número máximo de resultados. Default: 10

### search_cleanup

Limpia el historial de búsqueda antiguo (entradas mayores a 30 días).

### search_stats

Muestra estadísticas del caché e historial.

## Sistema de Caché

### Estructura

```
.search/
├── cache/                           # Caché permanente
│   └── {hash_query}/
│       ├── results.md
│       └── query.txt
├── history/                        # Historial de 30 días
│   └── {timestamp}/
│       ├── results.md
│       └── query.txt
└── .search.db                      # Índice de codesearch
```

### Cómo Funciona el Caché

```
1. Query: "Google Gemini MCP"
2. Hash: SHA256("google gemini mcp") = "a7f3b2c1..."
3. ¿Existe cache/a7f3b2c1/?
   - SÍ → Retorna resultados en caché (0 tokens)
   - NO → Busca, guarda en caché, retorna resultados
```

### Comparación de Costos

| Método | Primera Vez | Repetida |
|--------|-------------|----------|
| `search` | 100-500 tokens | 100-500 tokens |
| `search_cached` | 100-500 tokens | **0 tokens** |
| codesearch en caché | 0 tokens | 0 tokens |

## Integración con codesearch

### Flujo de Trabajo

```text
1. search_cached("query")        → Busca y guarda en caché
2. codesearch index              → Indexa .search/
3. codesearch search "pregunta" → Consulta sin costo de API
```

### Comandos

```bash
# Buscar con caché (recomendado)
search_cached("Google Gemini MCP")

# Mostrar estadísticas
search_stats()

# Limpiar historial antiguo
search_cleanup()
```

## Ejemplo de Ahorro de Tokens

| Escenario | Sin Caché | Con Caché | Ahorro |
|----------|-----------|-----------|--------|
| 1 query | 500 tokens | 500 tokens | 0% |
| 5 queries (1 repetida) | 2500 tokens | 1000 tokens | 60% |
| 10 queries (todas únicas) | 5000 tokens | 5000 tokens | 0% |
| 10 queries (todas repetidas) | 5000 tokens | 500 tokens | **90%** |