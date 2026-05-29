# Jurispeed.ai Challenge

Mini-orquestador multi-agente en Python para el challenge tecnico de Jurispeed.ai.

La implementacion principal usa la Anthropic Python SDK directa con `tool_use` nativo. El codigo deja una capa `AIProvider` para no acoplar todo el sistema al SDK, pero la ruta recomendada y priorizada para este challenge es Anthropic directo.

## Alcance

- Orquestador Indigo `#6366f1`.
- Agente Litigante Azul `#3b82f6`.
- Agente Normativo Ambar `#f59e0b`.
- Busquedas locales sobre `mock_data.json`.
- Historial conversacional en memoria.
- CLI interactivo y demo de los 3 turns obligatorios.
- Interfaz web con Flask + Vue.
- Tests unitarios sin llamadas reales al LLM.

## Instalacion

Inicializacion recomendada:

```bash
./scripts/bootstrap.sh
source .venv/bin/activate
```

Si prefieres hacerlo manualmente:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Si cambias dependencias del proyecto mas adelante, vuelve a correr:

```bash
pip install -e ".[dev]"
```

Luego edita `.env`:

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

## Ejecucion

CLI interactivo:

```bash
jurispeed-challenge
```

Demo con los 3 turns obligatorios:

```bash
jurispeed-challenge --demo
```

Sin instalar el script, tambien puedes usar:

```bash
PYTHONPATH=src python -m jurispeed_challenge.cli --demo
```

Interfaz web:

```bash
jurispeed-challenge-web
```

Luego abre `http://127.0.0.1:5000`.

## Como funciona

El sistema tiene tres agentes:

- `OrchestratorAgent`: decide a que agente especializado consultar y redacta la respuesta final.
- `LitiganteAgent`: busca jurisprudencia en `mock_data.json`.
- `NormativoAgent`: busca normativa en `mock_data.json`.

El flujo es este:

1. El usuario escribe una pregunta en el CLI.
2. El Orquestador envia esa pregunta a Claude con una lista de herramientas disponibles.
3. Claude puede pedir `route_to_litigante`, `route_to_normativo` o ambas.
4. El loop de `tool_use` ejecuta la herramienta local correspondiente.
5. El resultado vuelve al modelo como `tool_result`.
6. Claude sintetiza una respuesta final usando solo la evidencia encontrada.

Ese loop manual vive en [tool_loop.py](jurispeed-challenge/src/jurispeed_challenge/tool_loop.py) y es la pieza central del challenge.

La interfaz web agrega una capa Flask + Vue por encima del mismo orquestador:

- Flask expone `/api/chat`, `/api/state`, `/api/session/reset` y sirve la pagina principal.
- Vue renderiza el chat, el historial, el estado de carga y las herramientas usadas.
- La sesion conversacional sigue siendo en memoria, solo que ahora se asocia a una cookie de sesion del navegador.
- Para mantener el setup liviano del challenge, Vue se carga desde CDN en la pagina web.

## Tests

```bash
pytest
```

Los tests mockean el proveedor y no llaman a Anthropic. Esto valida que el loop de `tool_use`:

- Recibe un bloque `tool_use`.
- Ejecuta la herramienta local.
- Responde con `tool_result` inmediatamente despues del mensaje del assistant.
- Continua hasta obtener texto final.

## Configuracion de proveedores

El switch global recomendado vive en `.env`:

```bash
GLOBAL_AI_PROVIDER=anthropic
GLOBAL_AI_MODEL=claude-sonnet-4-5-20250929
```

Con eso solo, el sistema completo usa Anthropic para todos los roles.

Tambien hay overrides por rol:

```bash
# JURISPEED_ORCHESTRATOR_PROVIDER=anthropic
# JURISPEED_ORCHESTRATOR_MODEL=claude-sonnet-4-5-20250929
# JURISPEED_LITIGANTE_PROVIDER=anthropic
# JURISPEED_NORMATIVO_PROVIDER=anthropic
```

Dejalos comentados si quieres que `GLOBAL_AI_PROVIDER` controle todo el sistema.

La seleccion del proveedor ocurre en [ai_providers.py](jurispeed-challenge/src/jurispeed_challenge/ai_providers.py:79):

- `AnthropicProvider` usa `ANTHROPIC_API_KEY`.
- `BedrockProvider` existe como adaptador secundario, pero no es el camino principal del challenge.

Si alguna vez quisieras llevar el costo a AWS, tambien se puede usar Amazon Bedrock mediante `AnthropicBedrock`:

```bash
GLOBAL_AI_PROVIDER=bedrock
GLOBAL_AI_MODEL=global.anthropic.claude-sonnet-4-5-20250929-v1:0
AWS_PROFILE=default
AWS_REGION=us-east-1
```

Para Bedrock, este proyecto instala `boto3` y `botocore[crt]` para que el cliente pueda ejecutar requests reales contra AWS, incluyendo metodos de autenticacion modernos como perfiles de login.

La logica queda asi:

- `GLOBAL_AI_PROVIDER` y `GLOBAL_AI_MODEL`: switch global para todo el sistema.
- `JURISPEED_ORCHESTRATOR_*`, `JURISPEED_LITIGANTE_*`, `JURISPEED_NORMATIVO_*`: overrides por agente si alguna vez los necesitas.

## Decision clave

La busqueda documental es mockeada y deterministica por requerimiento del challenge. El LLM se usa para orquestacion, uso de herramientas y sintesis, no como fuente primaria de datos juridicos.

Si `search_jurisprudencia` devuelve `count=0`, el sistema debe reconocer que no encontro jurisprudencia en el mock y no debe inventar roles, tribunales ni sentencias.

## Arquitectura

```text
Usuario / CLI
  -> OrquestadorAgent
      -> route_to_litigante
          -> LitiganteAgent
              -> search_jurisprudencia(mock_data.json)
      -> route_to_normativo
          -> NormativoAgent
              -> search_normativa(mock_data.json)
      -> synthesize
  -> respuesta final
```

Cada agente obtiene su proveedor desde `ProviderResolver`, que lee un registro estandar por rol. Hoy todos usan Anthropic, pero el resto del codigo no depende directamente del SDK.

## Limitaciones conocidas

- La persistencia de historial es en memoria; para produccion usaria DynamoDB con TTL y particion por usuario/tenant.
- La busqueda esta basada en palabras clave sobre mock data; en produccion seria OpenSearch KNN con embeddings, filtros por permisos y reranking.
- El resultado real depende de fondos/API key de Anthropic; los tests cubren el loop de tools sin red.
