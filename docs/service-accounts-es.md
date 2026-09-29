# Cuentas de servicio — `arl-dtpr-dev-mdm-country-sync`

Registro de todas las cuentas de servicio (service accounts) que existen y se
usan activamente en este proyecto, para qué sirve cada una, y qué permisos
tiene exactamente.

> Número de proyecto: **`<PROJECT_NUMBER>`** (verificado con
> `gcloud projects describe arl-dtpr-dev-mdm-country-sync --format="value(projectNumber)"`).

---

## 1. `sa-cloudrun-mdmsync@arl-dtpr-dev-mdm-country-sync.iam.gserviceaccount.com`

**Nombre:** `sa-cloudrun-mdmsync`

**Convención de nombre:** `sa-<tipo-de-componente>-<alias-del-dominio>`. El
último segmento literal del project ID (`sync`) era poco descriptivo, así
que se usó `mdmsync` en su lugar (decisión explícita).

**Para qué se usa:** identidad de ejecución **compartida por las 2 Cloud
Run** de este proyecto:
- `cr-mdm-ingest-country`
- `cr-crud-mdm-country-api`

**Permisos que tiene:**
| Rol | Alcance | Para qué |
|---|---|---|
| `roles/bigquery.dataEditor` | Datasets `raw_arl_all_restcountries` y `std_arl_all_restcountries` únicamente | `cr-mdm-ingest-country` inserta en `country_raw`; `cr-crud-mdm-country-api` inserta en `trx_crud_action`. Se otorga con `GRANT ... ON SCHEMA` (DCL de BigQuery); se retiró el permiso que tenía a nivel de proyecto |
| `roles/bigquery.jobUser` | Todo el proyecto | Ejecutar los jobs de inserción |
| `roles/datastore.user` | Todo el proyecto | `cr-crud-mdm-country-api` lee/escribe la colección `countries` en Firestore |
| `roles/pubsub.publisher` | Tópico `mdm-country-updates` | `cr-crud-mdm-country-api` publica un evento por cada cambio real (el CRUD es la única vía de escritura al maestro) |
| `roles/logging.logWriter` | Todo el proyecto | Logs estructurados de ambos servicios |

---

## 2. `sa-cloudfunction-mdmsync@arl-dtpr-dev-mdm-country-sync.iam.gserviceaccount.com`

**Nombre:** `sa-cloudfunction-mdmsync`

**Para qué se usa:** identidad de ejecución **compartida por las 2 Cloud
Functions** de este proyecto:
- `cf-update-mdm-country`
- `cf-notify-downstream`

**Permisos que tiene:**
| Rol | Alcance | Para qué |
|---|---|---|
| `roles/bigquery.dataViewer` | Solo el dataset `std_arl_all_restcountries` | `cf-update-mdm-country` solo **lee** `trx_country_change`. Antes tenía `dataEditor` a nivel de proyecto, que sobraba porque la función no escribe en BigQuery |
| `roles/bigquery.jobUser` | Todo el proyecto | Ejecutar el job de consulta |
| `roles/logging.logWriter` | Todo el proyecto | Logs estructurados de ambas funciones |
| `roles/run.invoker` | `cf-notify-downstream` y `cr-crud-mdm-country-api` | Toda Cloud Function gen2 corre sobre un servicio Cloud Run interno: el trigger de Pub/Sub invoca a `cf-notify-downstream` con esta identidad, y `cf-update-mdm-country` llama al CRUD con un token OIDC de esta cuenta |
| ~~`roles/datastore.user`~~ y ~~`roles/pubsub.publisher`~~ | — | **Retirados el 25/09/2026**: `cf-update-mdm-country` ya no escribe en Firestore ni publica; lo hace el CRUD. Verificado con el Workflow en `Succeeded` |
| `roles/iam.serviceAccountTokenCreator` (otorgado *sobre* esta cuenta, no *por* ella) | — | El agente de servicio de Pub/Sub (`service-<PROJECT_NUMBER>@gcp-sa-pubsub.iam.gserviceaccount.com`) necesita este rol sobre `sa-cloudfunction-mdmsync` para invocar `cf-notify-downstream` (trigger de Pub/Sub) |

---

## 3. `sa-workflow-mdmsync@arl-dtpr-dev-mdm-country-sync.iam.gserviceaccount.com`

**Nombre:** `sa-workflow-mdmsync`

**Para qué se usa:** identidad del Workflow `orquestador-mdm-country-sync`,
que encadena en una sola ejecución los 3 pasos manuales (ingesta →
detección de cambios → sincronización).

**Permisos que tiene:**
| Rol | Alcance | Para qué |
|---|---|---|
| `roles/run.invoker` | `cr-mdm-ingest-country` | Llamar la Cloud Run de ingesta vía OIDC |
| `roles/run.invoker` | `cf-update-mdm-country` | Llamar la Cloud Function de sincronización vía OIDC |
| Rol personalizado `mdmTransferRunner` (`bigquery.transfers.get`, `bigquery.transfers.update`) | Todo el proyecto | Disparar y consultar manualmente `sq_detect_country_changes` vía la API de BigQuery Data Transfer |
| `roles/logging.logWriter` | Todo el proyecto | Logs de ejecución del Workflow |

**Por qué un rol personalizado en vez de uno predefinido:** no existe un rol
predefinido de GCP con exactamente `bigquery.transfers.get` +
`bigquery.transfers.update` sin permisos adicionales.

```bash
gcloud iam roles create mdmTransferRunner \
  --project=arl-dtpr-dev-mdm-country-sync \
  --title="MDM Transfer Runner" \
  --description="Permiso mínimo para disparar y consultar manualmente la Scheduled Query sq_detect_country_changes" \
  --permissions=bigquery.transfers.get,bigquery.transfers.update
```

---

## 4. `<PROJECT_NUMBER>-compute@developer.gserviceaccount.com`

**Nombre:** Default compute service account (cuenta autogenerada por GCP)

**Estado actual (tras el hardening de IAM): sin uso y sin permisos de proyecto.**
- **Cloud Build** usa `sa-cloudbuild-mdmsync` (`--build-service-account` en cada `gcloud run deploy` / `gcloud functions deploy`).
- La **BigQuery Scheduled Query** `sq_detect_country_changes` corre como `sa-scheduledquery-mdmsync` (sigue **on-demand**).

**Permisos que tiene:** ninguno de proyecto. Se le retiró `roles/editor` (heredado al crearla) y también el `roles/storage.objectViewer` que habíamos agregado a mano en el primer despliegue (ver nota histórica abajo). Se verificó con el Workflow, con los redespliegues del Cloud Run y de la Cloud Function, y con la API CRUD.

> **Nota histórica.** El primer `gcloud run deploy --source .` de este proyecto falló con `PERMISSION_DENIED` al leer el zip fuente, porque esta cuenta no tenía permisos sobre Storage en un proyecto recién creado; se resolvió dándole `roles/storage.objectViewer`. Con `sa-cloudbuild-mdmsync` (`roles/run.builder`) ya no hace falta. Si se despliega **sin** `--build-service-account`, GCP vuelve a usar esta cuenta y el error reaparece.

---

## 5. `sa-scheduledquery-mdmsync@arl-dtpr-dev-mdm-country-sync.iam.gserviceaccount.com`

**Para qué se usa:** identidad de ejecución de la Scheduled Query `sq_detect_country_changes` (antes: la cuenta default de Compute). Se configura en la consola: Edit → Schedule → Update scheduled query → Service account.

**Permisos que tiene:**
| Rol | Alcance | Para qué |
|---|---|---|
| `roles/bigquery.jobUser` | Proyecto | Ejecutar la query |
| `roles/bigquery.dataViewer` | Dataset `raw_arl_all_restcountries` | Leer `country_raw` |
| `roles/bigquery.dataEditor` | Dataset `std_arl_all_restcountries` | Escribir `trx_country_change` y actualizar `ori_ref_country` (`MERGE`) |

**Cuidado al guardar:** ese panel también trae **Schedule options**. Antes de **Save**, dejar **Repeat frequency = On-demand**; si no, el panel puede activar un horario cada hora.

**Verificación:** el `user_email` del job `scheduled_query_<id>` en `INFORMATION_SCHEMA.JOBS_BY_PROJECT` es esta cuenta. `bq show --transfer_config` no sirve para eso: `ownerInfo.email` puede seguir mostrando la cuenta de Compute.

---

## 6. `sa-cloudbuild-mdmsync@arl-dtpr-dev-mdm-country-sync.iam.gserviceaccount.com`

**Para qué se usa:** identidad de **Cloud Build** en los despliegues del Cloud Run y de las Cloud Functions, indicada con `--build-service-account`.

**Permisos que tiene:** `roles/run.builder` (proyecto). Verificado también para builds de Cloud Functions gen2.

---

## 7. `arl-dtpr-dev-mdm-country-sync@appspot.gserviceaccount.com`

**Nombre:** cuenta default de App Engine (autogenerada por GCP, no la creamos nosotros). Ningún componente la usa. Tenía `roles/editor` heredado; se retiró y se verificó con el Workflow y los redespliegues.

---

## Resumen

| Cuenta | Tipo | Usada por | Permiso principal |
|---|---|---|---|
| `sa-cloudrun-mdmsync` | Creada a propósito | `cr-mdm-ingest-country`, `cr-crud-mdm-country-api` | `bigquery.dataEditor` (solo `raw_` y `std_`), `bigquery.jobUser`, `datastore.user`, `logging.logWriter`, `pubsub.publisher` (tópico) |
| `sa-cloudfunction-mdmsync` | Creada a propósito | `cf-update-mdm-country`, `cf-notify-downstream` | `bigquery.dataViewer` (solo `std_`), `bigquery.jobUser`, `logging.logWriter`, `run.invoker` (sobre `cf-notify-downstream` y el CRUD) |
| `sa-workflow-mdmsync` | Creada a propósito | `orquestador-mdm-country-sync` | `run.invoker` (x2 servicios) + rol personalizado `mdmTransferRunner` |
| `sa-scheduledquery-mdmsync` | Creada a propósito (hardening) | Scheduled Query `sq_detect_country_changes` | `bigquery.jobUser` + `dataViewer` en `raw_` + `dataEditor` en `std_` |
| `sa-cloudbuild-mdmsync` | Creada a propósito (hardening) | Cloud Build (deploys) | `run.builder` |
| `<PROJECT_NUMBER>-compute@developer.gserviceaccount.com` | Automática (default) | **Ningún componente** | Sin `roles/editor` ni `storage.objectViewer` (retirados) |
| `arl-dtpr-dev-mdm-country-sync@appspot.gserviceaccount.com` | Automática (App Engine) | **Ningún componente** | Sin `roles/editor` (retirado) |

## Notas de diseño

- **Un service account por tipo de componente, no por instancia**: las 2
  Cloud Run comparten `sa-cloudrun-mdmsync`; las 2 Cloud Functions comparten
  `sa-cloudfunction-mdmsync`; el Workflow tiene su propia cuenta porque es un
  tipo de componente distinto.
- **Incidente de permisos en proyecto recién creado**: este proyecto no
  tenía la cuenta de compute con permisos suficientes para que Cloud Build
  leyera el código fuente en el primer despliegue — se resolvió otorgando
  `roles/storage.objectViewer` explícitamente. Vale la pena revisar esto al
  crear futuros proyectos nuevos desde cero.
