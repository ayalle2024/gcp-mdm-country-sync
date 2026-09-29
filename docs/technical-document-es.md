# Documento Técnico de Despliegue
## MDM Countries Sync (`arl-dtpr-dev-mdm-country-sync`)

**Autor:** Alvaro Yalle
**Organización:** Arla & Asociados
**Última actualización:** 28/09/2026

---

## 1. Resumen del proyecto

| Campo | Valor |
|---|---|
| Project ID | `arl-dtpr-dev-mdm-country-sync` |
| Número de proyecto | `<PROJECT_NUMBER>` |
| Región | `us-central1` (BigQuery y Data Transfer en `us`) |
| Taxonomía | `<bu>-<capability>-<env>-<domain>` → `arl` (Arla & Asociados) · `dtpr` (Data Products) · `dev` · `mdm-country-sync` (MDM de países) |
| Patrón que demuestra | Gestión de datos maestros (MDM): ingesta desde una API pública, detección de cambios contra un snapshot, sincronización a un maestro vivo, notificación aguas abajo por eventos, API CRUD y auditoría |
| Fuente de datos | API pública `countries.dev` (`GET https://countries.dev/countries`), 250 países, sin key |
| Maestro vivo | Firestore, colección `countries` |
| Sistema downstream simulado | Un webhook de [webhook.site](https://webhook.site) |
| Costo | $0.00 — dentro del free tier permanente de GCP |

### 1.1. Qué hace el proyecto, en una frase
Cada ejecución trae los 250 países de una API pública, detecta con BigQuery qué países son nuevos o cambiaron respecto al snapshot vigente y envía esos cambios a la API CRUD, que es la **única vía de escritura al maestro** en Firestore: escribe solo lo que cambió, deja la auditoría en BigQuery y publica un evento por cada cambio real, que `cf-notify-downstream` reenvía a un sistema downstream. Un Cloud Workflow encadena todo. La misma API CRUD atiende también, de forma manual, consultas y modificaciones del maestro con el mismo tratamiento (validación, auditoría y evento).

### 1.2. Fuente de datos reemplazada
El proyecto original usaba REST Countries v3.1, que quedó deprecada (la v5 exige API key con cuota de 500 requests/mes). Se reemplazó por `countries.dev`: misma cobertura, esquema casi idéntico, sin key, sin registro y sin cuota mensual. El mapeo cambia en `alpha3Code`, `name` y `capital` (texto plano en lugar de arreglo).

### 1.3. Inventario de componentes (12)

| # | Tipo | Nombre | Rol en el flujo |
|---|---|---|---|
| 1 | Cloud Workflow | `orquestador-mdm-country-sync` | Orquesta ingesta → detección → sincronización |
| 2 | Cloud Run | `cr-mdm-ingest-country` | Consulta `countries.dev` e inserta en la capa raw |
| 3 | BigQuery (tabla) | `raw_arl_all_restcountries.country_raw` | Capa raw: una fila por país por corrida |
| 4 | BigQuery Scheduled Query | `sq_detect_country_changes` | Detecta cambios y actualiza el snapshot |
| 5 | BigQuery (tabla) | `std_arl_all_restcountries.ori_ref_country` | Snapshot vigente de cada país |
| 6 | BigQuery (tabla) | `std_arl_all_restcountries.trx_country_change` | Auditoría de cambios (INSERT / UPDATE) |
| 7 | Cloud Function | `cf-update-mdm-country` | Lee los cambios desde el inicio de la ejecución (since) y los envía por lotes al CRUD |
| 8 | Firestore | colección `countries` | Maestro vivo (lo escribe solo el CRUD) |
| 9 | Pub/Sub | `mdm-country-updates` | Bus de eventos de cambio (lo publica el CRUD) |
| 10 | Cloud Function | `cf-notify-downstream` | Notifica al sistema downstream (webhook) |
| 11 | Cloud Run | `cr-crud-mdm-country-api` | Única vía de escritura al maestro: valida, escribe, audita y publica (lo usan el flujo automático y las llamadas manuales) |
| 12 | BigQuery (tabla) | `std_arl_all_restcountries.trx_crud_action` | Auditoría de cada acción del CRUD, manual o automática |

Los 12 componentes forman el flujo orquestado: `cf-update-mdm-country` (7) escribe el maestro **a través** de `cr-crud-mdm-country-api` (11), que deja la auditoría en `trx_crud_action` (12) y publica en `mdm-country-updates` (9). Además, el CRUD atiende llamadas manuales.

---

## 2. Arquitectura

```
Workflow: orquestador-mdm-country-sync  (botón Execute · sa-workflow-mdmsync)
   │
   ├─► Paso 1: POST (OIDC) ─► Cloud Run: cr-mdm-ingest-country ──► countries.dev (250 países)
   │                                   └─► BigQuery raw: country_raw
   │
   ├─► Paso 2: Scheduled Query sq_detect_country_changes (dispara y espera con polling)
   │                          ├─► BigQuery std: trx_country_change   (INSERT / UPDATE)
   │                          └─► BigQuery std: ori_ref_country      (snapshot, MERGE)
   │
   └─► Paso 3: POST (OIDC) ─► Cloud Function: cf-update-mdm-country (HTTP)
                                   │  lee los cambios desde el inicio de la ejecución (trx_country_change)
                                   └─► POST /sync/countries (OIDC, lotes de 100)
                                              ▼
                                Cloud Run: cr-crud-mdm-country-api   ← única vía de escritura al maestro
                                   ├─► Firestore: countries            (solo si el dato cambió)
                                   ├─► BigQuery std: trx_crud_action   (auditoría de cada cambio)
                                   └─► Pub/Sub: mdm-country-updates    (un evento por cambio real)
                                              │  (automático, Eventarc)
                                              ▼
                                Cloud Function: cf-notify-downstream ─► Webhook downstream

Entrada manual (la misma API, mismos tres destinos):
Cliente ─► cr-crud-mdm-country-api  (GET / POST / PUT / DELETE /countries)
```

### 2.1. Orden real de ejecución
1. Workflow `orquestador-mdm-country-sync` (botón **Execute**).
2. Cloud Run `cr-mdm-ingest-country` → inserta 250 filas en `country_raw`.
3. Scheduled Query `sq_detect_country_changes` → `trx_country_change` y `ori_ref_country`.
4. Cloud Function `cf-update-mdm-country` → envía al CRUD los cambios desde el inicio de la ejecución (since), en lotes de 100.
5. Cloud Run `cr-crud-mdm-country-api` → compara con Firestore; por cada país nuevo o modificado escribe, audita y publica un evento; los que no cambiaron (`NO_CHANGE`) solo se auditan.
6. Cloud Function `cf-notify-downstream` (se dispara sola por Pub/Sub, sin que el Workflow la llame) → webhook.

### 2.2. Dos entradas de datos, un solo camino de escritura
| | Entrada 1: API externa | Entrada 2: llamada manual |
|---|---|---|
| Origen de los datos | `countries.dev` (250 países) | Quien llame a la API CRUD |
| Disparo | Workflow, o `curl` | Bajo demanda |
| Camino | `cr-mdm-ingest-country` → BigQuery → `cf-update-mdm-country` → **CRUD** | **CRUD** |
| Escribe el maestro | Solo el CRUD | Solo el CRUD |
| Auditoría (`caller`) | `cf-update-mdm-country` | `manual` (o el valor de la cabecera `X-Caller`) |
| Evento en Pub/Sub | Uno por cambio real | Uno por cambio real |

Como las dos entradas pasan por el mismo componente, reciben la misma validación, idempotencia, auditoría y notificación. Un dato editado a mano se conserva hasta que la API externa cambie ese país; entonces `cf-update-mdm-country` lo sobrescribe a través del CRUD y se publica el evento.

## 3. Prerrequisitos

### 3.1. Cuenta y herramientas
```bash
gcloud auth login
gcloud config set project arl-dtpr-dev-mdm-country-sync
```
Python 3.11 para las pruebas locales del Cloud Run (las Cloud Functions usan 3.12); `uv` opcional para generar `requirements.txt`.

### 3.2. Habilitar las APIs
```bash
gcloud services enable \
  run.googleapis.com cloudfunctions.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com eventarc.googleapis.com pubsub.googleapis.com \
  bigquery.googleapis.com bigquerydatatransfer.googleapis.com firestore.googleapis.com \
  workflows.googleapis.com iam.googleapis.com \
  --project=arl-dtpr-dev-mdm-country-sync
```
Si el primer deploy de Workflow falla con `Workflows service agent does not exist (Code: 9)` (error transitorio tras habilitar la API):
```bash
gcloud beta services identity create --service=workflows.googleapis.com --project=arl-dtpr-dev-mdm-country-sync
```

### 3.3. Cuenta de Cloud Build
Todos los despliegues usan `sa-cloudbuild-mdmsync` con `--build-service-account` (sección 5.4): no se depende de la cuenta default de Compute.

> **Nota histórica.** En este proyecto recién creado, el primer `gcloud run deploy --source .` falló con `PERMISSION_DENIED ... IAM permission denied for service account ...-compute@developer.gserviceaccount.com`, porque la cuenta de Compute no podía leer el zip de código. Entonces se resolvió con `roles/storage.objectViewer`; ese permiso ya se retiró porque con `sa-cloudbuild-mdmsync` no hace falta. Si se despliega **sin** `--build-service-account`, GCP vuelve a usar la cuenta de Compute y el error reaparece.

### 3.4. Base de datos Firestore (una sola vez)
Debe crearse **sin `--database`** para obtener la base especial `(default)` (elegible para free tier y la que usa el cliente de Python por defecto):
```bash
gcloud firestore databases create --location=us-central1 --type=firestore-native \
  --project=arl-dtpr-dev-mdm-country-sync
```
> **Trampa de la consola:** escribir `default` (sin poder teclear los paréntesis) en "Database ID" crea una base **con nombre**, no elegible para free tier y distinta de la que usa el código.

---

## 4. Notas de costo

| Servicio | Límite gratuito permanente | Uso en el proyecto |
|---|---|---|
| BigQuery | 1 TB consultas/mes + 10 GB | ~250 filas por corrida |
| Firestore | 1 GB + 50 K lecturas / 20 K escrituras diarias | 250 documentos; un listado completo cuesta 250 lecturas |
| Cloud Run | 2 M requests/mes | Un request por ejecución |
| Cloud Functions | 2 M invocaciones/mes | Una del Workflow más una por evento |
| Pub/Sub | 10 GB/mes | Mensajes de pocos bytes |
| Cloud Workflows | 5 000 pasos internos/mes | ~30 pasos por ejecución |

Detalle en [`costs-es.md`](costs-es.md).

---

## 5. Cuentas de servicio (IAM)

Convención: `sa-<tipo-de-componente>-<alias>`: **una cuenta por tipo de componente, no por instancia**. El alias es `mdmsync`, porque el último segmento del project ID (`sync`) es poco descriptivo.

| Cuenta | Tipo | Usada por |
|---|---|---|
| `sa-cloudrun-mdmsync` | Cloud Run | `cr-mdm-ingest-country`, `cr-crud-mdm-country-api` |
| `sa-cloudfunction-mdmsync` | Cloud Function | `cf-update-mdm-country`, `cf-notify-downstream` y su trigger de Pub/Sub |
| `sa-workflow-mdmsync` | Workflow | `orquestador-mdm-country-sync` |
| `sa-scheduledquery-mdmsync` | Scheduled Query | `sq_detect_country_changes` |
| `sa-cloudbuild-mdmsync` | Cloud Build | Deploys de Cloud Run y Cloud Functions (`--build-service-account`) |
| `<PROJECT_NUMBER>-compute@developer.gserviceaccount.com` | Automática (default) | **Ningún componente**; se le retiraron `roles/editor` y `storage.objectViewer` |
| `arl-dtpr-dev-mdm-country-sync@appspot.gserviceaccount.com` | Automática (App Engine) | **Ningún componente**; se le retiró `roles/editor` |

> Estado tras el hardening de IAM (24/09/2026): ningún componente depende de las cuentas default. Verificado con el Workflow en `Succeeded`, con redespliegues del Cloud Run y de la Cloud Function en `SUCCESS` con `sa-cloudbuild-mdmsync`, y con la API CRUD. Guía completa: [`iam-hardening-es.md`](iam-hardening-es.md).

### 5.1. Creación
```bash
P=arl-dtpr-dev-mdm-country-sync
for SA in sa-cloudrun-mdmsync sa-cloudfunction-mdmsync sa-workflow-mdmsync sa-scheduledquery-mdmsync sa-cloudbuild-mdmsync; do
  gcloud iam service-accounts create $SA --project=$P
done
```

### 5.2. Permisos de `sa-cloudrun-mdmsync`
| Rol | Alcance | Para qué |
|---|---|---|
| `roles/bigquery.dataEditor` | Datasets `raw_` y `std_` (`GRANT ... ON SCHEMA`) | `cr-mdm-ingest-country` inserta en `country_raw`; `cr-crud-mdm-country-api` inserta en `trx_crud_action` |
| `roles/bigquery.jobUser` | Proyecto | Ejecutar jobs de inserción |
| `roles/datastore.user` | Proyecto | `cr-crud-mdm-country-api` lee y escribe Firestore |
| `roles/pubsub.publisher` | Tópico `mdm-country-updates` | `cr-crud-mdm-country-api` publica un evento por cada cambio real |
| `roles/logging.logWriter` | Proyecto | Logs estructurados |

```bash
gcloud pubsub topics add-iam-policy-binding mdm-country-updates \
  --member="serviceAccount:sa-cloudrun-mdmsync@arl-dtpr-dev-mdm-country-sync.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher"
```

### 5.3. Permisos de `sa-cloudfunction-mdmsync`
| Rol | Alcance | Para qué |
|---|---|---|
| `roles/bigquery.dataViewer` | Dataset `std_` | `cf-update-mdm-country` solo **lee** `trx_country_change` |
| `roles/bigquery.jobUser` | Proyecto | Ejecutar la consulta |
| `roles/logging.logWriter` | Proyecto | Logs estructurados |
| `roles/run.invoker` | Servicios `cf-notify-downstream` y `cr-crud-mdm-country-api` | El trigger de Pub/Sub invoca a `cf-notify-downstream` con esta identidad, y `cf-update-mdm-country` llama al CRUD con un token OIDC de esta cuenta |
| `roles/iam.serviceAccountTokenCreator` (otorgado *sobre* esta cuenta) | Al agente de Pub/Sub `service-<PROJECT_NUMBER>@gcp-sa-pubsub.iam.gserviceaccount.com` | Poder generar tokens OIDC al invocar `cf-notify-downstream` |

> Con el diseño actual (un solo camino de escritura), esta cuenta **ya no tiene** `roles/datastore.user` ni `roles/pubsub.publisher`: `cf-update-mdm-country` no escribe en Firestore ni publica, lo hace el CRUD. Se retiraron el 25/09/2026 y se verificó con el Workflow.

```bash
P=arl-dtpr-dev-mdm-country-sync
CF=sa-cloudfunction-mdmsync@$P.iam.gserviceaccount.com
for ROLE in roles/bigquery.jobUser roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding $P --member="serviceAccount:$CF" --role="$ROLE"
done
gcloud iam service-accounts add-iam-policy-binding $CF \
  --member="serviceAccount:service-<PROJECT_NUMBER>@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```
(`roles/run.invoker` se otorga tras desplegar cada componente; ver 9.3.)

### 5.4. Cuentas de la Scheduled Query y de Cloud Build
```bash
gcloud projects add-iam-policy-binding $P --member="serviceAccount:sa-scheduledquery-mdmsync@$P.iam.gserviceaccount.com" --role="roles/bigquery.jobUser"
gcloud projects add-iam-policy-binding $P --member="serviceAccount:sa-cloudbuild-mdmsync@$P.iam.gserviceaccount.com" --role="roles/run.builder"
```
Los permisos por dataset son SQL: se ejecutan con `bq query <<'EOF' ... EOF` o en BigQuery Studio, no se pegan sueltos en la terminal:
```sql
-- Scheduled Query: lee raw, escribe std
GRANT `roles/bigquery.dataViewer` ON SCHEMA `arl-dtpr-dev-mdm-country-sync.raw_arl_all_restcountries`
  TO "serviceAccount:sa-scheduledquery-mdmsync@arl-dtpr-dev-mdm-country-sync.iam.gserviceaccount.com";
GRANT `roles/bigquery.dataEditor` ON SCHEMA `arl-dtpr-dev-mdm-country-sync.std_arl_all_restcountries`
  TO "serviceAccount:sa-scheduledquery-mdmsync@arl-dtpr-dev-mdm-country-sync.iam.gserviceaccount.com";
-- Cloud Run: escribe en raw (ingesta) y en std (auditoría CRUD)
GRANT `roles/bigquery.dataEditor` ON SCHEMA `arl-dtpr-dev-mdm-country-sync.raw_arl_all_restcountries`
  TO "serviceAccount:sa-cloudrun-mdmsync@arl-dtpr-dev-mdm-country-sync.iam.gserviceaccount.com";
GRANT `roles/bigquery.dataEditor` ON SCHEMA `arl-dtpr-dev-mdm-country-sync.std_arl_all_restcountries`
  TO "serviceAccount:sa-cloudrun-mdmsync@arl-dtpr-dev-mdm-country-sync.iam.gserviceaccount.com";
-- Cloud Functions: solo lee std
GRANT `roles/bigquery.dataViewer` ON SCHEMA `arl-dtpr-dev-mdm-country-sync.std_arl_all_restcountries`
  TO "serviceAccount:sa-cloudfunction-mdmsync@arl-dtpr-dev-mdm-country-sync.iam.gserviceaccount.com";
```
Todos los despliegues llevan `--build-service-account=projects/arl-dtpr-dev-mdm-country-sync/serviceAccounts/sa-cloudbuild-mdmsync@arl-dtpr-dev-mdm-country-sync.iam.gserviceaccount.com`. `run.builder` alcanza también para builds de Cloud Functions gen2 (verificado).

### 5.5. Permisos de `sa-workflow-mdmsync`
```bash
gcloud iam roles create mdmTransferRunner --project=$P \
  --title="MDM Transfer Runner" --permissions=bigquery.transfers.get,bigquery.transfers.update

W=sa-workflow-mdmsync@$P.iam.gserviceaccount.com
gcloud projects add-iam-policy-binding $P --member="serviceAccount:$W" --role="projects/$P/roles/mdmTransferRunner"
gcloud projects add-iam-policy-binding $P --member="serviceAccount:$W" --role="roles/logging.logWriter"
```
Además `roles/run.invoker` sobre `cr-mdm-ingest-country` (7.4) y sobre `cf-update-mdm-country` (9.3).

### 5.6. Regla de oro de IAM
Los permisos tardan 1–2 minutos en propagarse: ante un `403` recién otorgado, esperar y reintentar. Tras **retirar** un permiso conviene esperar varios minutos antes de probar, para no obtener un falso positivo por propagación.

---

## 6. Capa de datos

### 6.1. BigQuery — dataset `raw_arl_all_restcountries` (región `US`)
**`country_raw`**: una fila por país por corrida, campos tal como los devuelve la fuente, sin validación. Particionada por `DATE(ingestion_timestamp)`, clusterizada por `country_code`.

| Columna | Tipo | Descripción |
|---|---|---|
| `country_code` | STRING NOT NULL | Código ISO de 3 letras (`alpha3Code` en la fuente) |
| `name_common` | STRING NOT NULL | Nombre común |
| `capital` | STRING | Capital (puede ser `NULL`, p. ej. Antártida) |
| `population` | INT64 | Población total |
| `region` | STRING | Región geográfica |
| `currency_code` | STRING | Código de la primera moneda (puede ser `NULL`) |
| `ingestion_timestamp` | TIMESTAMP NOT NULL | Momento UTC de ingesta; columna de partición |

### 6.2. BigQuery — dataset `std_arl_all_restcountries` (región `US`)
**`ori_ref_country`**: snapshot vigente de cada país, dato de referencia transversal. Sin partición.

| Columna | Tipo | Descripción |
|---|---|---|
| `country_code` | STRING NOT NULL | Llave primaria |
| `name` | STRING NOT NULL | Nombre común |
| `capital`, `region`, `currency_code` | STRING | Atributos vigentes |
| `population` | INT64 | Población según la última sincronización |
| `last_synced_at` | TIMESTAMP NOT NULL | Última actualización desde raw |

**`trx_country_change`**: un registro por cambio detectado. Particionada por `DATE(detected_at)`, clusterizada por `country_code`.

| Columna | Tipo | Descripción |
|---|---|---|
| `change_id` | STRING NOT NULL | UUID del cambio |
| `country_code` | STRING NOT NULL | FK hacia `ori_ref_country` |
| `change_type` | STRING NOT NULL | `INSERT` (país nuevo) o `UPDATE` (país modificado) |
| `field_changed` | STRING | Primer campo distinto (`name`, `capital`, `population`, `region`, `currency_code`); `NULL` en un INSERT |
| `old_value` / `new_value` | STRING | Estado anterior / nuevo, serializado en JSON |
| `detected_at` | TIMESTAMP NOT NULL | Momento de detección; partición |

**`trx_crud_action`**: una fila por acción de la API CRUD. Particionada por `DATE(performed_at)`, clusterizada por `country_code`.

| Columna | Tipo | Descripción |
|---|---|---|
| `action_id` | STRING NOT NULL | UUID de la acción |
| `action_type` | STRING NOT NULL | `CREATE`, `READ`, `UPDATE` o `DELETE` |
| `country_code` | STRING | País afectado (vacío en el listado completo) |
| `performed_at` | TIMESTAMP NOT NULL | Momento de la acción; partición |
| `source` | STRING NOT NULL | Servicio origen (`cr-crud-mdm-country-api`) |
| `result` | STRING | `CREATED`, `UPDATED`, `NO_CHANGE`, `DELETED` u `OK` (lecturas) |
| `caller` | STRING | Quién llamó al CRUD: `manual` o el valor de la cabecera `X-Caller` (p. ej. `cf-update-mdm-country`) |
| `payload` | STRING | Datos enviados, serializados en JSON |

### 6.3. Creación
```bash
bq query --use_legacy_sql=false < bigquery/country_raw.sql
bq query --use_legacy_sql=false < bigquery/ori_ref_country.sql
bq query --use_legacy_sql=false < bigquery/trx_country_change.sql
bq query --use_legacy_sql=false < bigquery/trx_crud_action.sql
```
Los DDL de `country_raw` y `ori_ref_country` incluyen `CREATE SCHEMA IF NOT EXISTS` para su dataset.

### 6.4. Firestore — colección `countries`
| Campo | Valor |
|---|---|
| Base | `(default)`, Native mode, `us-central1` |
| Colección | `countries` |
| Clave del documento | `country_code` |
| Escrita por | Solo `cr-crud-mdm-country-api` (`set(..., merge=True)`), alimentado por `cf-update-mdm-country` y por las llamadas manuales |

Documento que escribe el CRUD al sincronizar (los campos los arma `cf-update-mdm-country`):
```json
{
  "country_code": "AFG", "name": "Afghanistan", "capital": "Kabul",
  "population": 40218234, "region": "Asia", "currency_code": "AFN",
  "last_change_type": "INSERT", "last_change_id": "b30d62ec-87be-4997-a4ca-942ca66cc1f2"
}
```
Es el **estado actual** del maestro; el histórico vive en `trx_country_change`. Para una prueba limpia no hay `TRUNCATE`: en la consola, colección → ⋮ → **Delete collection**.

### 6.5. Pub/Sub — `mdm-country-updates`
```bash
gcloud pubsub topics create mdm-country-updates
```
Lo publica `cr-crud-mdm-country-api` (un mensaje por cada cambio real: `country_code`, `change_type` [`INSERT`, `UPDATE` o `DELETE`], `field_changed` y `source`) y lo consume `cf-notify-downstream`. Las sincronizaciones sin cambios (`NO_CHANGE`) no publican nada. La suscripción la crea Eventarc al desplegar con `--trigger-topic`. Con política `RETRY_POLICY_DO_NOT_RETRY`, un webhook que falla pierde ese mensaje.

---

## 7. Cloud Run — `cr-mdm-ingest-country`

| Campo | Valor |
|---|---|
| Acceso | Privado (`--no-allow-unauthenticated`) |
| Identidad | `sa-cloudrun-mdmsync` |
| URL | `https://cr-mdm-ingest-country-<PROJECT_NUMBER>.us-central1.run.app` |
| Rutas | `GET/POST /` y `GET/POST /mdm-ingest-country` |
| Arquitectura | En capas: `src/app/{main.py, api/routes/ingestion.py, core/config.py, integrations/{countriesdev,bigquery}/main.py, services/ingestion_service.py, utils/}` |
| Tests | 17, todos pasando |
| Tiempo máximo | 300 s |

### 7.1. Qué hace
1. `fetch_all_countries()` llama a `countries.dev` con timeout de 20 s. Convierte fallos de red, respuesta no JSON o no-lista en `CountriesApiError`.
2. `clean_record()` aplana cada país: `alpha3Code → country_code`, `name → name_common`, `capital`, `population`, `region` y `currencies[0].code → currency_code`, con `ingestion_timestamp` UTC.
3. `is_valid_record()` descarta países sin `country_code` o sin nombre (`skipped`).
4. `insert_country_rows()` inserta todo en `country_raw` en **una sola llamada** (`insert_rows_json`); un error de BigQuery se convierte en `BigQueryInsertError`.
5. Responde `{"status":"success","service":...,"payload":{"inserted":250,"skipped":0,"ingestion_timestamp":...}}`. Errores de la API o de BigQuery → HTTP 502; cualquier otro → 500.

### 7.2. Variables de entorno
| Variable | Default |
|---|---|
| `PROJECT_ID` | `arl-dtpr-dev-mdm-country-sync` |
| `SERVICE_NAME` | `cr-mdm-ingest-country` |
| `COUNTRIES_API_URL` | `https://countries.dev/countries` |
| `BQ_RAW_DATASET` | `raw_arl_all_restcountries` |
| `BQ_RAW_TABLE` | `country_raw` |

### 7.3. Despliegue
```bash
cd cloud-run/cr-mdm-ingest-country
P=arl-dtpr-dev-mdm-country-sync
gcloud run deploy cr-mdm-ingest-country \
  --source . --region us-central1 --no-allow-unauthenticated \
  --service-account=sa-cloudrun-mdmsync@$P.iam.gserviceaccount.com \
  --build-service-account=projects/$P/serviceAccounts/sa-cloudbuild-mdmsync@$P.iam.gserviceaccount.com \
  --set-env-vars=PROJECT_ID=$P,SERVICE_NAME=cr-mdm-ingest-country,COUNTRIES_API_URL=https://countries.dev/countries,BQ_RAW_DATASET=raw_arl_all_restcountries,BQ_RAW_TABLE=country_raw
```
> Verificar antes con `unzip -l` que el zip sea el de `cr-mdm-ingest-country` (con `countriesdev` y `bigquery`) y que use el `Dockerfile`, no buildpacks.

### 7.4. Permiso para el Workflow
```bash
gcloud run services add-iam-policy-binding cr-mdm-ingest-country --region=us-central1 \
  --member="serviceAccount:sa-workflow-mdmsync@$P.iam.gserviceaccount.com" --role="roles/run.invoker"
```

### 7.5. Prueba directa
```bash
curl -X POST https://cr-mdm-ingest-country-<PROJECT_NUMBER>.us-central1.run.app/ \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)"
# {"payload":{"inserted":250,"skipped":0,...},"service":"cr-mdm-ingest-country","status":"success"}
```

---

## 8. BigQuery Scheduled Query — `sq_detect_country_changes`

| Campo | Valor |
|---|---|
| Modo | **On-demand** (no corre sola; la dispara el Workflow o "Run transfer now") |
| Identidad | `sa-scheduledquery-mdmsync` |
| Ubicación | `us` |
| Config ID (transfer) | `<ID_SQ_DETECT_COUNTRY_CHANGES>` |
| SQL | `scheduled-queries/sq_detect_country_changes.sql` |

**Qué hace, en 2 sentencias:**
1. **`INSERT` en `trx_country_change`:** toma, para cada país, la ingesta más reciente de `country_raw` (`ARRAY_AGG(... ORDER BY ingestion_timestamp DESC LIMIT 1)`, por si hubo varias corridas) y la compara con `ori_ref_country`. Si el país no existe → `INSERT`; si algún campo cambió → `UPDATE` con el primer campo distinto. Guarda el estado anterior y el nuevo en JSON.
2. **`MERGE` en `ori_ref_country`:** actualiza el snapshot con el estado más reciente (`WHEN MATCHED` actualiza, `WHEN NOT MATCHED` inserta).

La comparación usa `IS DISTINCT FROM` y no `!=`, porque `capital` y `currency_code` pueden ser `NULL` (Antártida) y `NULL != NULL` no es `TRUE` en SQL estándar. Si los datos no cambiaron, la primera sentencia inserta **0 filas**, por lo que ejecuciones repetidas no generan cambios.

### 8.1. Creación (consola)
1. Pegar el SQL en BigQuery Studio y ejecutarlo una vez.
2. **Schedule → Create new scheduled query**, nombre `sq_detect_country_changes`.
3. **Repeat frequency = On-demand**, ubicación `us`, **Service account = `sa-scheduledquery-mdmsync`**.
4. Anotar el `transferConfigId` (`bq ls --transfer_config --transfer_location=us --project_id=arl-dtpr-dev-mdm-country-sync`); se usa en el Workflow.

### 8.2. Cambiar la cuenta (siempre por la consola)
Edit → Schedule → Update scheduled query. Antes de **Save**, poner **Repeat frequency = On-demand**; si no, el panel puede activar `every 1 hours` y la query empieza a correr sola. `bq update --service_account_name` no es fiable (reporta éxito sin aplicar el cambio). Para confirmar la identidad real, consultar `user_email` de los jobs:
```sql
SELECT job_id, user_email, creation_time
FROM `region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE job_id LIKE 'scheduled_query_%' ORDER BY creation_time DESC LIMIT 4;
```
Comprobar que no tiene horario: `bq show --format=prettyjson --transfer_config projects/<PROJECT_NUMBER>/locations/us/transferConfigs/<ID_SQ_DETECT_COUNTRY_CHANGES> | grep -E '"(schedule|nextRunTime|disabled)"'` no debe devolver nada.

---

## 9. Cloud Functions (2)

En los comandos de las secciones 9 y 10 se usa `P=arl-dtpr-dev-mdm-country-sync`.

Ambas: gen2, Python 3.12, `us-central1`, identidad `sa-cloudfunction-mdmsync`, sin acceso público, con la **arquitectura plana**:
```
main.py                # from src.main import main
src/{config.py, gcp_logging.py, main.py, utils.py}
tests/                 # conftest.py, test_logging.py, test_main.py, test_utils.py
requirements.txt · Procfile · pytest.ini · .gcloudignore · .gitignore
```

### 9.1. `cf-update-mdm-country`

| Campo | Valor |
|---|---|
| Trigger | HTTP (signature type `http`) |
| URL directa | `<URL_CF_UPDATE_MDM_COUNTRY>` |
| Tiempo máximo / memoria | 60 s / 256 MB |
| Tests | 22 |

**Qué hace:**
1. Lee `since` del cuerpo de la petición (lo envía el Workflow, con la hora de inicio de la ejecución) y responde HTTP 400 si falta. `get_changes_since(since)` consulta `trx_country_change` con `detected_at >= @since`, ordenado por `detected_at`.
2. `build_country_data()` convierte cada cambio (`new_value` en JSON) en el documento del maestro (`name_common → name`, más `last_change_type` y `last_change_id`).
3. `sync_changes_via_crud()` obtiene un token OIDC con la URL del CRUD como audiencia y envía los cambios en lotes de `CRUD_SYNC_CHUNK_SIZE` (100) a `POST /sync/countries`, con la cabecera `X-Caller: cf-update-mdm-country`. Suma los contadores de cada lote y, si el CRUD responde con estado ≥ 300, lanza un error.
4. Responde `{"synced": N, "created": a, "updated": b, "unchanged": c}` con HTTP 200; si no hay cambios desde `since`, no llama al CRUD y responde todo en 0.

La función **ya no escribe en Firestore ni publica en Pub/Sub**: lo hace el CRUD, que decide qué cambió de verdad.

**Corregido el 28/09/2026:** antes tomaba todos los cambios con fecha de hoy (`DATE(detected_at) = CURRENT_DATE()`), así que un segundo Execute el mismo día reenviaba cambios ya aplicados; si mientras tanto alguien editaba un país a mano, el reenvío lo revertía. Ahora filtra por `since`, la hora exacta de inicio de la ejecución: un segundo Execute sin cambios nuevos da `synced: 0` (verificado). Sigue habiendo una segunda capa de seguridad: aunque se reenviara un cambio viejo, el CRUD es idempotente y da `NO_CHANGE` sin escribir ni publicar.

**Rendimiento:** con 500 cambios en un Execute, el Workflow completo (ingesta + Scheduled Query + sincronización) tarda ~1 min 40 s. No se midió la función de forma aislada; su tiempo máximo sigue siendo 60 s, y cada lote de 100 cambios es una sola llamada al CRUD (una lectura por lote en Firestore, una escritura por lote, una inserción de auditoría y las publicaciones). Si el volumen creciera mucho, se puede subir el tiempo máximo (`--timeout`).

| Variable | Default |
|---|---|
| `PROJECT_ID` / `REGION` | `arl-dtpr-dev-mdm-country-sync` / `us-central1` |
| `SERVICE_NAME` | `cf-update-mdm-country` |
| `BQ_DATASET` | `std_arl_all_restcountries` |
| `BQ_CHANGE_TABLE` | `trx_country_change` |
| `CRUD_API_URL` | `https://cr-crud-mdm-country-api-<PROJECT_NUMBER>.us-central1.run.app` |
| `CRUD_SYNC_CHUNK_SIZE` | `100` |
| `CRUD_TIMEOUT_SECONDS` | `120` |

Dependencias: `functions-framework`, `google-cloud-bigquery`, `google-auth`, `requests`.

```bash
gcloud functions deploy cf-update-mdm-country \
  --gen2 --runtime=python312 --region=us-central1 --source=. \
  --entry-point=main --trigger-http \
  --service-account=sa-cloudfunction-mdmsync@$P.iam.gserviceaccount.com \
  --build-service-account=projects/$P/serviceAccounts/sa-cloudbuild-mdmsync@$P.iam.gserviceaccount.com \
  --no-allow-unauthenticated \
  --set-env-vars=PROJECT_ID=$P,REGION=us-central1,SERVICE_NAME=cf-update-mdm-country,BQ_DATASET=std_arl_all_restcountries,BQ_CHANGE_TABLE=trx_country_change,CRUD_API_URL=https://cr-crud-mdm-country-api-<PROJECT_NUMBER>.us-central1.run.app,CRUD_SYNC_CHUNK_SIZE=100,CRUD_TIMEOUT_SECONDS=120
```

### 9.2. `cf-notify-downstream`

| Campo | Valor |
|---|---|
| Trigger | Pub/Sub → `mdm-country-updates` (signature type `event`) |
| Tests | 9 |

**Qué hace:** decodifica el evento (base64) y hace `POST` con `requests` al webhook `WEBHOOK_URL` (simula el sistema downstream, p. ej. Salesforce), con timeout configurable. Si responde con estado ≥ 300 lanza `RuntimeError`. No toca BigQuery.

| Variable | Default |
|---|---|
| `PROJECT_ID` / `REGION` | `arl-dtpr-dev-mdm-country-sync` / `us-central1` |
| `SERVICE_NAME` | `cf-notify-downstream` |
| `WEBHOOK_URL` | `https://webhook.site/CHANGE-ME` (se configura al desplegar) |
| `WEBHOOK_TIMEOUT_SECONDS` | `10` |

```bash
gcloud functions deploy cf-notify-downstream \
  --gen2 --runtime=python312 --region=us-central1 --source=. \
  --entry-point=main --trigger-topic=mdm-country-updates \
  --service-account=sa-cloudfunction-mdmsync@$P.iam.gserviceaccount.com \
  --build-service-account=projects/$P/serviceAccounts/sa-cloudbuild-mdmsync@$P.iam.gserviceaccount.com \
  --no-allow-unauthenticated \
  --set-env-vars=PROJECT_ID=$P,REGION=us-central1,SERVICE_NAME=cf-notify-downstream,WEBHOOK_URL=https://webhook.site/<TU-URL>,WEBHOOK_TIMEOUT_SECONDS=10
```

### 9.3. Permisos `run.invoker` tras cada despliegue
```bash
CF=sa-cloudfunction-mdmsync@$P.iam.gserviceaccount.com
for F in cf-notify-downstream cr-crud-mdm-country-api; do
  gcloud run services add-iam-policy-binding $F --region=us-central1 --member="serviceAccount:$CF" --role="roles/run.invoker"
done
# El Workflow invoca directamente la función HTTP
gcloud run services add-iam-policy-binding cf-update-mdm-country --region=us-central1 \
  --member="serviceAccount:sa-workflow-mdmsync@$P.iam.gserviceaccount.com" --role="roles/run.invoker"
```

### 9.4. Cambiar variables sin código fuente
`gcloud functions deploy` sin estar en la carpeta de la función falla con `Invalid value for [--source]`. Para cambiar solo variables (por ejemplo, un webhook nuevo):
```bash
gcloud run services update cf-notify-downstream --region=us-central1 \
  --project=arl-dtpr-dev-mdm-country-sync --update-env-vars=WEBHOOK_URL=https://webhook.site/<NUEVA-URL>
```

### 9.5. Pruebas
```bash
cd cloud-functions/<nombre> && pip install -r requirements.txt pytest && pytest tests/ -v
```

---

## 10. Cloud Run — `cr-crud-mdm-country-api` (única vía de escritura al maestro)

| Campo | Valor |
|---|---|
| Acceso | Privado |
| Identidad | `sa-cloudrun-mdmsync` |
| URL | `https://cr-crud-mdm-country-api-<PROJECT_NUMBER>.us-central1.run.app` |
| Arquitectura | En capas: `api/routes/countries.py`, `services/crud_service.py`, `integrations/{firestore,bigquery,pubsub}/main.py` |
| Tests | 63, todos pasando |
| Tiempo máximo | 300 s |

### 10.1. Qué hace cada operación que cambia el maestro
Siempre en este orden: **1)** escribe en Firestore, **2)** deja la auditoría en `trx_crud_action`, **3)** publica el evento en `mdm-country-updates`. Es **idempotente**: si el dato enviado no cambia ningún campo de negocio (`name`, `capital`, `population`, `region`, `currency_code`) respecto al guardado, responde `NO_CHANGE` y no escribe ni publica (solo audita). Los campos de metadatos (`last_change_id`, `last_change_type`) se guardan pero no cuentan como cambio.

### 10.2. Endpoints
| Método y ruta | Qué hace | Respuesta |
|---|---|---|
| `GET /countries` | Lista todos los países (sin paginación) | 200 |
| `GET /countries/<code>` | Devuelve un país | 200 / 404 |
| `POST /countries/<code>` | Crea el país. Si ya existe idéntico → `NO_CHANGE`; si existe con datos distintos → conflicto | 201 (`CREATED`) / 200 (`NO_CHANGE`) / 409 |
| `PUT /countries/<code>` | Actualiza con `merge`. Si nada cambia → `NO_CHANGE` | 200 / 404 |
| `DELETE /countries/<code>` | Borra el documento y publica el evento `DELETE` | 200 / 404 |
| `POST /sync/countries` | **Lote** de altas y cambios: `{"changes":[{"country_code","data":{...}}]}` (máximo 500). Devuelve `{"total","created","updated","unchanged"}` | 200 / 400 |

El código se convierte a mayúsculas. Errores de auditoría o de Pub/Sub → `502`; solicitud inválida → `400`. Cabecera opcional `X-Caller`: se guarda en la auditoría (`manual` por defecto). Los eventos usan el mismo contrato de siempre, más `source`: `{"country_code","change_type","field_changed","source"}`.

**Limitación conocida:** si Firestore se escribe pero falla la publicación en Pub/Sub, el CRUD responde `502` y un reintento del mismo dato daría `NO_CHANGE`, con lo que ese evento se perdería (no hay patrón *outbox*).

### 10.3. Variables de entorno
| Variable | Default |
|---|---|
| `PROJECT_ID` / `SERVICE_NAME` | `arl-dtpr-dev-mdm-country-sync` / `cr-crud-mdm-country-api` |
| `FIRESTORE_COLLECTION` | `countries` |
| `BQ_DATASET` / `BQ_AUDIT_TABLE` | `std_arl_all_restcountries` / `trx_crud_action` |
| `OUTPUT_PUBSUB_TOPIC` | `mdm-country-updates` |
| `PUBLISH_TO_OUTPUT_TOPIC` | `true` (permite desactivar la publicación) |
| `SYNC_MAX_BATCH` | `500` |

Dependencias: `flask`, `gunicorn`, `google-cloud-firestore`, `google-cloud-bigquery`, `google-cloud-pubsub`.

### 10.4. Despliegue y prueba
Antes de desplegar por primera vez la versión con eventos: ampliar la tabla de auditoría (`bigquery/migrations/trx_crud_action_alter_v2.sql`, que agrega `result`, `caller` y `payload`) y dar `roles/pubsub.publisher` sobre el tópico a `sa-cloudrun-mdmsync` (5.2).
```bash
cd cloud-run/cr-crud-mdm-country-api
gcloud run deploy cr-crud-mdm-country-api \
  --source . --region us-central1 --no-allow-unauthenticated \
  --service-account=sa-cloudrun-mdmsync@$P.iam.gserviceaccount.com \
  --build-service-account=projects/$P/serviceAccounts/sa-cloudbuild-mdmsync@$P.iam.gserviceaccount.com \
  --set-env-vars=PROJECT_ID=$P,SERVICE_NAME=cr-crud-mdm-country-api,FIRESTORE_COLLECTION=countries,BQ_DATASET=std_arl_all_restcountries,BQ_AUDIT_TABLE=trx_crud_action,OUTPUT_PUBSUB_TOPIC=mdm-country-updates

URL=https://cr-crud-mdm-country-api-<PROJECT_NUMBER>.us-central1.run.app
curl "$URL/countries/AFG" -H "Authorization: Bearer $(gcloud auth print-identity-token)"
```
Auditoría de las acciones (ordenar por hora, no por la primera columna, que es un UUID):
```sql
SELECT action_type, country_code, result, caller, performed_at
FROM `std_arl_all_restcountries.trx_crud_action` ORDER BY performed_at DESC LIMIT 10;
```

## 11. Cloud Workflow — `orquestador-mdm-country-sync`

| Campo | Valor |
|---|---|
| Región | `us-central1` |
| Identidad | `sa-workflow-mdmsync` |
| Definición | `workflow/orquestador-mdm-country-sync.yaml` |
| Variables | `workflow/env.yaml` |

### 11.1. Variables de entorno del Workflow (8, sin cambios de nombre; el Workflow ahora también arma `since` internamente con `time.format(sys.now())`, no es una variable de entorno)
| Variable | Valor |
|---|---|
| `project_id` | `arl-dtpr-dev-mdm-country-sync` |
| `project_number` | `<PROJECT_NUMBER>` |
| `region` | `us-central1` |
| `transfer_location` | `us` |
| `cloud_run_service_name` | `cr-mdm-ingest-country` |
| `transfer_config_id` | `<ID_SQ_DETECT_COUNTRY_CHANGES>` |
| `poll_interval_seconds` | `10` |
| `cf_update_mdm_country_url` | `<URL_CF_UPDATE_MDM_COUNTRY>` |

### 11.2. Pasos
| Paso | Qué hace |
|---|---|
| `init` | Lee las 8 variables y construye la URL de Cloud Run y el nombre del transfer config |
| `call_ingest` | `http.post` OIDC a `cr-mdm-ingest-country`, con `try/except` que expone el error real |
| `log_ingest_result` / `check_ingest_status` | Registra la respuesta y exige `body.status == "success"` |
| `trigger_scheduled_query` → `extract_run_name` | Dispara `sq_detect_country_changes` con `startManualRuns` |
| `check_transfer_run_status` → `evaluate_transfer_status` → `wait_before_retry` | Polling cada 10 s: `SUCCEEDED` continúa, `FAILED`/`CANCELLED` termina con error y detalle |
| `call_update_mdm_country` | `http.post` OIDC a `cf-update-mdm-country`, con `try/except` |
| `workflow_success` | Devuelve `ingest_result`, `scheduled_query_final_state` y `update_result` |

`cf-notify-downstream` **no** se llama desde el Workflow: se dispara sola por su trigger de Pub/Sub cuando `cr-crud-mdm-country-api` (el CRUD) publica un evento real.

### 11.3. Resultado esperado
```json
{
  "ingest_result": {"payload": {"inserted": 250, "skipped": 0, "ingestion_timestamp": "2026-09-28T17:55:54.742410+00:00"}, "service": "cr-mdm-ingest-country", "status": "success"},
  "scheduled_query_final_state": "SUCCEEDED",
  "update_result": {"synced": 3, "created": 3, "updated": 0, "unchanged": 0}
}
```
`synced` es el número de cambios detectados **desde el inicio de esta ejecución** (`since`), y `created`, `updated` y `unchanged` son lo que el CRUD hizo con ellos. Este es el resultado real de la ejecución `aa82e4e8-9ced-4989-b04b-981ec4a18645` (28/09/2026), tras borrar 3 países de prueba con el CRUD y quitarlos de `ori_ref_country`: el Workflow los detecta como altas nuevas (`INSERT`) y el CRUD los crea. Una segunda ejecución sin cambios nuevos da `{"synced": 0, "created": 0, "updated": 0, "unchanged": 0}` (verificado, ejecución de las 17:51–17:53 UTC).

### 11.4. Creación (siempre por la consola)
1. **Workflows → Create**: nombre `orquestador-mdm-country-sync`, región `us-central1`, service account `sa-workflow-mdmsync`.
2. En **Environment variables**, cargar las 8 variables de 11.1.
3. **Next** → pegar el YAML → **Deploy**.

### 11.5. Ejecución (siempre con el botón Execute)
Workflows → `orquestador-mdm-country-sync` → **Execute** con entrada `{}`.

### 11.6. Errores típicos
| Error | Causa | Solución |
|---|---|---|
| `403` al llamar a Cloud Run o a la función justo tras otorgar `run.invoker` | Propagación de IAM | Esperar 1–2 min y reintentar |
| `403 Forbidden ... insufficient_scope` | Barra `/` final en la URL de Cloud Run (el audience OIDC no coincide) | Construir la URL sin `/` final. **Corregido el 28/09/2026:** el Workflow desplegado ya arma la URL sin la barra final |
| `IAM permission denied for service account sa-workflow-mdmsync` | Falta `run.invoker` o no propagó | Otorgarlo y esperar |
| `Workflows service agent does not exist (Code: 9)` | API recién habilitada | `gcloud beta services identity create --service=workflows.googleapis.com` |

---

## 12. Webhook downstream simulado

`cf-notify-downstream` publica en un webhook de [webhook.site](https://webhook.site) (variable `WEBHOOK_URL`). Limitación de la versión gratuita sin cuenta: tope **de por vida de 50 requests almacenados por URL**; al alcanzarlo, todo request devuelve `429 Request limit exceeded` de forma permanente. Solución: generar una URL nueva y actualizarla con `gcloud run services update ... --update-env-vars` (9.4). Como el tópico no reintenta, los mensajes rechazados se pierden.

Como el CRUD es idempotente, solo se publica un evento por cambio real (`CREATED`, `UPDATED` o `DELETED`); las sincronizaciones sin cambios (`NO_CHANGE`) no publican nada, y no consumen el tope. Una carga completa desde cero (250 altas) sí lo supera.

---

## 13. Checklist de verificación (capturas para el documento E2E)

- [ ] `orquestador-mdm-country-sync`: ejecución en `Succeeded` con el grafo de pasos
- [ ] `cr-mdm-ingest-country`: logs con `INICIO … / FIN CR MDM INGEST COUNTRY OK` y `inserted: 250`
- [ ] `country_raw` con 250 filas por corrida
- [ ] Scheduled Query `sq_detect_country_changes`: ejecución exitosa en el historial
- [ ] `ori_ref_country` con 250 países y `trx_country_change` con los cambios detectados
- [ ] `cf-update-mdm-country`: logs con `Cambios detectados desde: <since>`, `Cambios de esta ejecución: N`, `Resultado de la sincronización vía CRUD: {...}` y `FIN … OK`
- [ ] Firestore `countries` con un documento por país
- [ ] Pub/Sub `mdm-country-updates` con su suscripción de Eventarc
- [ ] `cf-notify-downstream`: logs con el evento reenviado
- [ ] Requests recibidos en el webhook
- [ ] `cr-crud-mdm-country-api`: `GET /countries/AFG` y filas de auditoría en `trx_crud_action` (con `result` y `caller`)

### 13.1. Prueba limpia (E2E desde cero)
```sql
TRUNCATE TABLE `raw_arl_all_restcountries.country_raw`;
TRUNCATE TABLE `std_arl_all_restcountries.ori_ref_country`;
TRUNCATE TABLE `std_arl_all_restcountries.trx_country_change`;
TRUNCATE TABLE `std_arl_all_restcountries.trx_crud_action`;
```
Se usa `TRUNCATE`, nunca `DROP`. Vaciar Firestore (⋮ → Delete collection) es opcional. Ojo: si además se vacía Firestore, el siguiente Execute detecta 250 altas y el CRUD publica 250 eventos (`CREATED`), con lo que se agota el tope de 50 requests; conviene tener una URL nueva antes. Si solo se vacía `ori_ref_country`, la sincronización da `unchanged` y no publica nada.

### 13.1.1. Pruebas del camino único de escritura (realizadas el 25/09/2026)
| Prueba | Resultado |
|---|---|
| `POST /countries/ZZZ` nuevo | `CREATED`, HTTP 201 |
| Mismo `POST` repetido | `NO_CHANGE`, HTTP 200, sin evento |
| `POST` del mismo país con datos distintos | HTTP 409 |
| `POST /sync/countries` con 1 país nuevo y 1 igual | `created: 1, unchanged: 1` |
| Auditoría | Filas con `result` y `caller` correctos (`manual`, `prueba-manual`) |
| Vaciar `ori_ref_country` + Execute (250 altas ya en Firestore) | `synced: 250, unchanged: 250`, 250 filas `NO_CHANGE` con `caller = cf-update-mdm-country`, **ningún evento** |
| `PUT` de `AFG` (población 1) + vaciar `ori_ref_country` + Execute | `updated: 1`; `AFG` recupera `40218234`; 2 eventos en el webhook (`source: manual` y `source: cf-update-mdm-country`), ninguno de otros países |
| Retirar `datastore.user` y `pubsub.publisher` de `sa-cloudfunction-mdmsync` + Execute | `Succeeded`, todo `unchanged` |

### 13.2. Prueba manual paso a paso (sin Workflow)
```bash
curl -X POST https://cr-mdm-ingest-country-<PROJECT_NUMBER>.us-central1.run.app/ -H "Authorization: Bearer $(gcloud auth print-identity-token)"
# BigQuery → Scheduled queries → sq_detect_country_changes → Run transfer now
curl -X POST <URL_CF_UPDATE_MDM_COUNTRY> \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d '{"since":"<timestamp>"}'
gcloud functions logs read cf-notify-downstream --region=us-central1 --gen2 --limit=20
```

---

## 14. Resumen de variables por componente

| Componente | Variables |
|---|---|
| `cr-mdm-ingest-country` | `PROJECT_ID`, `SERVICE_NAME`, `COUNTRIES_API_URL`, `BQ_RAW_DATASET`, `BQ_RAW_TABLE` |
| `cf-update-mdm-country` | `PROJECT_ID`, `REGION`, `SERVICE_NAME`, `BQ_DATASET`, `BQ_CHANGE_TABLE`, `CRUD_API_URL`, `CRUD_SYNC_CHUNK_SIZE`, `CRUD_TIMEOUT_SECONDS` |
| `cf-notify-downstream` | `PROJECT_ID`, `REGION`, `SERVICE_NAME`, `WEBHOOK_URL`, `WEBHOOK_TIMEOUT_SECONDS` |
| `cr-crud-mdm-country-api` | `PROJECT_ID`, `SERVICE_NAME`, `FIRESTORE_COLLECTION`, `BQ_DATASET`, `BQ_AUDIT_TABLE`, `OUTPUT_PUBSUB_TOPIC`, `PUBLISH_TO_OUTPUT_TOPIC`, `SYNC_MAX_BATCH` |
| Workflow | `project_id`, `project_number`, `region`, `transfer_location`, `cloud_run_service_name`, `transfer_config_id`, `poll_interval_seconds`, `cf_update_mdm_country_url` |

---

## 15. Observaciones de diseño

1. **Un solo camino de escritura.** Antes, la API externa escribía Firestore a través de `cf-update-mdm-country` y la API CRUD escribía directo por otro lado, sin publicar eventos. Ahora `cf-update-mdm-country` envía los cambios al CRUD y este es el único que escribe el maestro: validación, auditoría y un evento por cada cambio real. Los 12 componentes se mantienen; cambian las conexiones (`cf-update-mdm-country` → CRUD → Firestore, BigQuery y Pub/Sub).
2. **Decisiones de diseño del CRUD.** Se eligió Firestore como maestro en lugar de Cloud SQL, por costo (capa gratuita permanente, sin instancia que mantener encendida). No hay historial por versiones: cada cambio sobrescribe el documento vigente, no se guarda una fila por versión. La API es REST (`GET/POST/PUT/DELETE`), un endpoint por operación, en lugar de un único endpoint genérico con un parámetro que indique la acción. Y el CRUD no publica eventos cuando el resultado es `NO_CHANGE`, para no generar ruido en Pub/Sub ni gastar el tope del webhook con sincronizaciones que no cambiaron nada.
3. **Idempotencia.** Reenviar los mismos cambios (por ejemplo, un segundo Execute el mismo día) da `NO_CHANGE` y no genera eventos ni notificaciones.
4. **Precisión de los eventos.** Si Firestore se escribe pero falla la publicación, un reintento daría `NO_CHANGE` y ese evento se perdería (sin patrón *outbox*).
5. **Volumen.** `cr-mdm-ingest-country` inserta todo en una llamada (límite de BigQuery: 10 000 filas); `cf-update-mdm-country` envía lotes de 100 al CRUD (máximo 500 por solicitud); `GET /countries` no pagina.
6. **Cambio de comportamiento del `POST`.** Crear un país que ya existe con datos distintos ahora responde `409` (antes lo sobrescribía sin avisar).


## 16. Orden recomendado de despliegue desde cero

1. Crear proyecto y habilitar APIs (sección 3). No hace falta dar permisos a la cuenta de Compute.
2. Crear Firestore `(default)` por `gcloud` (3.4).
3. Crear el tópico Pub/Sub (6.5).
4. Crear datasets y tablas de BigQuery (6.3).
5. Crear las 5 cuentas de servicio y sus permisos (sección 5), con los permisos de BigQuery solo por dataset.
6. Ampliar `trx_crud_action` (`trx_crud_action_alter_v2.sql`), dar `pubsub.publisher` sobre el tópico a `sa-cloudrun-mdmsync` y desplegar `cr-mdm-ingest-country` (sección 7) y `cr-crud-mdm-country-api` (sección 10).
7. Generar una URL en webhook.site y desplegar las 2 Cloud Functions, con `CRUD_API_URL` apuntando al CRUD ya desplegado; otorgar `run.invoker` (sección 9.3, incluido el del CRUD).
8. Crear la Scheduled Query en on-demand y anotar su `transferConfigId` (sección 8).
9. Crear el Workflow desde la consola con sus 8 variables (sección 11).
10. Ejecutarlo con **Execute** y completar el checklist (sección 13). Al final, comprobar que las cuentas default de Compute y de App Engine no conservan `roles/editor`.
