# Hardening IAM — `arl-dtpr-dev-mdm-country-sync`
## Eliminar la dependencia de las cuentas default (`roles/editor`)

Guía ya aplicada y verificada el 24/09/2026.

**Objetivo:** que ningún componente use la cuenta default de Compute (`<PROJECT_NUMBER>-compute@…`) ni la default de App Engine (`arl-dtpr-dev-mdm-country-sync@appspot…`), ambas con `roles/editor` sobre todo el proyecto, y bajar los `bigquery.dataEditor` de proyecto a permisos por dataset.

## 1. Contexto del proyecto

| Tema | Diferencia en MDM |
|---|---|
| Scheduled Queries | **1** (`sq_detect_country_changes`): lee `raw_arl_all_restcountries` y escribe `std_arl_all_restcountries` |
| Cuenta de la query | Nueva `sa-scheduledquery-mdmsync` (alias `mdmsync`, porque el último segmento del project ID, `sync`, es poco descriptivo) |
| Identidad previa de la query | La cuenta default de Compute (un único job, del 18/09) |
| Cuentas con `dataEditor` de proyecto a acotar | **Dos**: `sa-cloudrun-mdmsync` y `sa-cloudfunction-mdmsync` |
| Permisos mínimos según el código | `cr-mdm-ingest-country` solo inserta en `raw_`; `cr-crud-mdm-country-api` solo inserta en `std_.trx_crud_action`; `cf-update-mdm-country` solo **lee** `std_.trx_country_change`; `cf-notify-downstream` no toca BigQuery |
| Permiso extra en la cuenta de Compute | `roles/storage.objectViewer`, agregado a mano en el primer despliegue; se retira al final |
| Cuenta default de App Engine | Existe con `roles/editor` y sin uso |

## 2. Estado final

| Cuenta | Usada por | Permisos |
|---|---|---|
| `sa-cloudrun-mdmsync` | `cr-mdm-ingest-country`, `cr-crud-mdm-country-api` | `bigquery.dataEditor` en `raw_` y `std_`, `bigquery.jobUser`, `datastore.user`, `logging.logWriter`, `pubsub.publisher` (tópico; agregado el 25/09 al pasar a un solo camino de escritura) |
| `sa-cloudfunction-mdmsync` | `cf-update-mdm-country`, `cf-notify-downstream` | `bigquery.dataViewer` en `std_`, `bigquery.jobUser`, `logging.logWriter`, `run.invoker` (sobre `cf-notify-downstream` y el CRUD). Se retiraron `datastore.user` y `pubsub.publisher` el 25/09 al pasar a un solo camino de escritura |
| `sa-workflow-mdmsync` | El Workflow | `run.invoker` (x2) + `mdmTransferRunner` + `logging.logWriter` *(sin cambios)* |
| `sa-scheduledquery-mdmsync` **(nueva)** | La Scheduled Query | `bigquery.jobUser` + `dataViewer` en `raw_` + `dataEditor` en `std_` |
| `sa-cloudbuild-mdmsync` **(nueva)** | Cloud Build (Cloud Run y Cloud Functions) | `roles/run.builder` |
| Compute y App Engine (default) | **Nadie** | Sin `roles/editor`; a Compute también se le retiró `storage.objectViewer` |

Orden seguido: primero lo aditivo, luego los cambios de comportamiento con prueba después de cada uno, y al final los retiros.

## 3. Pasos aplicados

### Fase A: crear y otorgar (no cambia ningún comportamiento)
```bash
PROJECT=arl-dtpr-dev-mdm-country-sync
gcloud iam service-accounts create sa-scheduledquery-mdmsync --display-name="Runtime identity for the Scheduled Query of mdm-country-sync"
gcloud iam service-accounts create sa-cloudbuild-mdmsync --display-name="Build identity for Cloud Run and Cloud Functions source deploys"

gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:sa-scheduledquery-mdmsync@$PROJECT.iam.gserviceaccount.com" --role="roles/bigquery.jobUser"
gcloud projects add-iam-policy-binding $PROJECT --member="serviceAccount:sa-cloudbuild-mdmsync@$PROJECT.iam.gserviceaccount.com" --role="roles/run.builder"
```
Permisos por dataset (SQL: se ejecutan con `bq query <<'EOF' … EOF` o en BigQuery Studio, no se pegan sueltos en la terminal):
```sql
GRANT `roles/bigquery.dataViewer` ON SCHEMA `arl-dtpr-dev-mdm-country-sync.raw_arl_all_restcountries` TO "serviceAccount:sa-scheduledquery-mdmsync@arl-dtpr-dev-mdm-country-sync.iam.gserviceaccount.com";
GRANT `roles/bigquery.dataEditor` ON SCHEMA `arl-dtpr-dev-mdm-country-sync.std_arl_all_restcountries` TO "serviceAccount:sa-scheduledquery-mdmsync@arl-dtpr-dev-mdm-country-sync.iam.gserviceaccount.com";
GRANT `roles/bigquery.dataEditor` ON SCHEMA `arl-dtpr-dev-mdm-country-sync.raw_arl_all_restcountries` TO "serviceAccount:sa-cloudrun-mdmsync@arl-dtpr-dev-mdm-country-sync.iam.gserviceaccount.com";
GRANT `roles/bigquery.dataEditor` ON SCHEMA `arl-dtpr-dev-mdm-country-sync.std_arl_all_restcountries` TO "serviceAccount:sa-cloudrun-mdmsync@arl-dtpr-dev-mdm-country-sync.iam.gserviceaccount.com";
GRANT `roles/bigquery.dataViewer` ON SCHEMA `arl-dtpr-dev-mdm-country-sync.std_arl_all_restcountries` TO "serviceAccount:sa-cloudfunction-mdmsync@arl-dtpr-dev-mdm-country-sync.iam.gserviceaccount.com";
```

### Fase B: cambios de comportamiento (con prueba después de cada uno)
1. **Scheduled Query con su cuenta (consola).** Scheduled queries → `sq_detect_country_changes` → Edit → Schedule → Update scheduled query: **Repeat frequency = On-demand** y **Service account = `sa-scheduledquery-mdmsync`** → Save. `bq update --service_account_name` no es fiable (reporta éxito sin aplicar el cambio). Prueba: Execute del Workflow y consulta de `user_email` de los jobs en `INFORMATION_SCHEMA.JOBS_BY_PROJECT`.
2. **Builds con su cuenta.** Redesplegar con `--build-service-account=projects/arl-dtpr-dev-mdm-country-sync/serviceAccounts/sa-cloudbuild-mdmsync@arl-dtpr-dev-mdm-country-sync.iam.gserviceaccount.com`: `cr-mdm-ingest-country` (Cloud Run) y `cf-update-mdm-country` (Cloud Function gen2). Comprobar con `gcloud builds list --region=us-central1`.
3. **Retirar el `dataEditor` de proyecto** a `sa-cloudrun-mdmsync` y a `sa-cloudfunction-mdmsync`. Pruebas: Execute del Workflow (inserción en `raw_`, query, lectura de `cf-update-mdm-country`) y un `GET /countries/AFG` a la API CRUD, que debe dejar una fila nueva en `std_.trx_crud_action`. Esperar unos minutos tras el retiro para que la prueba no sea un falso positivo por propagación.

### Fase C: retiros
```bash
PNUM=<PROJECT_NUMBER>
gcloud projects remove-iam-policy-binding $PROJECT --member="serviceAccount:$PNUM-compute@developer.gserviceaccount.com" --role="roles/editor"
gcloud projects remove-iam-policy-binding $PROJECT --member="serviceAccount:$PNUM-compute@developer.gserviceaccount.com" --role="roles/storage.objectViewer"
gcloud projects remove-iam-policy-binding $PROJECT --member="serviceAccount:$PROJECT@appspot.gserviceaccount.com" --role="roles/editor"
```
Prueba final: Execute del Workflow, redespliegue del Cloud Run y de la Cloud Function con `--build-service-account`, y un `GET` a la API CRUD.

**Rollback** (solo si hace falta volver atrás mientras se investiga):
```bash
gcloud projects add-iam-policy-binding arl-dtpr-dev-mdm-country-sync \
  --member="serviceAccount:<PROJECT_NUMBER>-compute@developer.gserviceaccount.com" --role="roles/editor"
```

## 4. Resultado de la aplicación (24/09/2026)

| Paso | Resultado |
|---|---|
| Fase A | 2 cuentas nuevas y 5 `GRANT` por dataset aplicados y verificados |
| B.1: identidad de la Scheduled Query | Verificado: los jobs de las 23:29, 23:40 y 23:59 UTC los ejecutó `sa-scheduledquery-mdmsync`; la query sigue sin horario |
| B.2: builds | Verificado: los builds de las 23:33, 23:34, 23:55 y 23:56 UTC usaron `sa-cloudbuild-mdmsync`; `run.builder` alcanza también para Cloud Functions gen2 |
| B.3: `dataEditor` de proyecto retirado | Verificado: Workflow en `Succeeded` y auditoría de la API CRUD escrita después del retiro |
| Fase C | Verificado: Workflow en `Succeeded` (23:59:43 UTC, `synced: 0`) y dos redespliegues en `SUCCESS` con las cuentas default sin permisos |

## 4.1. Ajuste posterior: un solo camino de escritura (25/09/2026)

Después del hardening, `cf-update-mdm-country` pasó a enviar los cambios a `cr-crud-mdm-country-api`, que es ahora la única vía de escritura al maestro (un solo camino de escritura). Cambios de IAM: `sa-cloudrun-mdmsync` **gana** `pubsub.publisher` sobre el tópico `mdm-country-updates`; `sa-cloudfunction-mdmsync` **gana** `run.invoker` sobre el CRUD y **pierde** `datastore.user` y `pubsub.publisher` (mejora el mínimo privilegio). Verificado con el Workflow en `Succeeded` tras retirar los dos permisos. Detalle en el documento técnico, secciones 5, 9.1 y 10.

## 5. Observaciones

- **`cf-update-mdm-country`** tardó ~15 s en procesar 250 cambios el 18/09 (tiempo máximo configurado: 60 s). No hay riesgo con el volumen actual.
- **(Resuelto el 28/09/2026) Sincronizaciones repetidas:** la función tomaba todos los cambios con fecha de hoy, por lo que un segundo Execute el mismo día volvía a sincronizarlos. Ahora el Workflow le envía `since` (inicio de la ejecución) y solo procesa los cambios de esa corrida; ver el documento técnico, sección 9.1.
- **(Resuelto)** Dos entradas de datos no conectadas: la API externa (vía `cr-mdm-ingest-country`) actualizaba el maestro a través de BigQuery y `cf-update-mdm-country`; la API CRUD escribía directo en Firestore y no publicaba eventos. Se decidió que `cf-update-mdm-country` llame al CRUD, que pasa a ser el único camino de escritura, con auditoría y publicación en Pub/Sub tras cada cambio real.
- **webhook.site:** no se consumió durante el hardening (`synced: 0`).
