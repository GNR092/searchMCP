# Agentes Especializados

## versionador

- Al crear un tag/version, **debe actualizar `pyproject.toml`** con el nuevo número de versión.
- Usa `tomllib` para leer/escribir `pyproject.toml` y actualizar el campo `version` en la sección `[project]`.
- Ejemplo: al crear `v1.4.0`, el archivo debe tener `version = "1.4.0"`.
- **Flujo esperado:**
  1. Detecta commits nuevos desde la última versión
  2. Clasifica si es `major`/`minor`/`patch` según Conventional Commits
  3. Crea el tag `vX.Y.Z`
  4. **Actualiza `pyproject.toml`** con el nuevo version
  5. Genera fragmento de CHANGELOG

## git

- **Después de hacer commits**, verificar si hay cambios en `pyproject.toml` (control de versión).
- Si `pyproject.toml` fue modificado (version bump), los commits deben incluirse en el tag.
- Flujo:
  1. `git commit -am "feat: ..."`
  2. `versionador` analiza los commits
  3. `versionador` crea tag y actualiza `pyproject.toml`
  4. `git` verifica que `pyproject.toml` tenga el version esperado
  5. `git push origin vX.Y.Z` (puede requerir `--force` si tag existía localmente)