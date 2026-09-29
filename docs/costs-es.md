# Costos de servicios — `arl-dtpr-dev-mdm-country-sync`

Servicios de GCP que usa el proyecto MDM Countries Sync, su capa gratuita y el gasto estimado.

> **Alcance de las cifras:** son una estimación a partir de lo desplegado y de las corridas de prueba (estado al 25/09/2026), no un dato de la consola de Facturación. El número exacto está en **Facturación → Informes**, filtrando por el proyecto `arl-dtpr-dev-mdm-country-sync`.

---

## Resumen

| Servicio | Uso en el proyecto | Free tier (mensual) | Costo estimado |
|---|---|---|---|
| BigQuery | 2 datasets (`raw_arl_all_restcountries`, `std_arl_all_restcountries`), 4 tablas, del orden de miles de filas entre todas | 10 GB de almacenamiento + 1 TB de consultas | **$0.00** |
| BigQuery Scheduled Query | 1 query (`sq_detect_country_changes`), on-demand, sin horario | Cuenta como una consulta normal | **$0.00** |
| Firestore | Base `(default)`, colección `countries` con 250 documentos | 1 GiB + 50 K lecturas y 20 K escrituras por día | **$0.00** |
| Cloud Run | 2 servicios propios (`cr-mdm-ingest-country`, `cr-crud-mdm-country-api`) + 2 servicios internos de las Cloud Functions gen2 | 180 000 vCPU-s + 360 000 GiB-s + 2 M de requests | **$0.00** |
| Cloud Functions (gen2) | 2 funciones (`cf-update-mdm-country` por HTTP, `cf-notify-downstream` por Pub/Sub) | 2 M de invocaciones (compartidas con Cloud Run) | **$0.00** |
| Pub/Sub | 1 tópico (`mdm-country-updates`), un mensaje por cambio real | 10 GB | **$0.00** |
| Cloud Workflows | 1 workflow (`orquestador-mdm-country-sync`), ejecución manual | 5 000 pasos internos y 2 000 llamadas HTTP gratuitos | **$0.00** |
| Cloud Build | Un build por cada despliegue de Cloud Run o de una función | 2 500 minutos | **$0.00** |
| Artifact Registry | Imágenes de contenedor de los 4 servicios | 0.5 GB | **$0.00** |

**Total estimado: $0.00 USD.** Los 9 servicios trabajan dentro de su capa gratuita con el volumen de las pruebas.

---

## Detalle

### BigQuery y Scheduled Query
- Dataset `raw_arl_all_restcountries` (tabla `country_raw`) y `std_arl_all_restcountries` (tablas `ori_ref_country`, `trx_country_change` y `trx_crud_action`).
- Cada ingesta agrega 250 filas a `country_raw`; `trx_crud_action` registra una fila por cada operación del CRUD, incluidas las sincronizaciones sin cambios. Con las pruebas, las cuatro tablas suman unos pocos miles de filas, muy por debajo de los límites.
- `sq_detect_country_changes` está en **on-demand**: no corre sola, se dispara desde el Workflow y se cobra como una consulta normal (por bytes procesados, una fracción mínima con estas tablas).

### Firestore
- Base `(default)` en modo Native, región `us-central1`; la capa gratuita solo aplica a la base especial `(default)`.
- El CRUD (`cr-crud-mdm-country-api`) es la única vía de escritura: escribe solo cuando un país cambia de verdad (`NO_CHANGE` no escribe). Cada sincronización lee los países del lote (hasta 500 por corrida), muy por debajo de las 50 000 lecturas diarias.

### Cloud Run y Cloud Functions gen2
- Los dos Cloud Run son privados; solo los invocan el Workflow y `cf-update-mdm-country`.
- `cf-update-mdm-country` envía los cambios al CRUD en lotes de 100, así que una corrida con 500 cambios equivale a 5 requests al CRUD.
- Cada Cloud Function gen2 corre sobre un servicio Cloud Run interno, por eso comparten la cuota gratuita de Cloud Run.

### Pub/Sub
- Un tópico. El CRUD publica un evento (menos de 1 KB) solo por cada cambio real; las sincronizaciones sin cambios no publican nada.

### Cloud Workflows
- Una ejecución manual por prueba, con decenas de pasos (llamadas HTTP y polling de la Scheduled Query cada 10 s), muy por debajo de los 5 000 pasos internos gratuitos al mes.

### Cloud Build y Artifact Registry
- Cada despliegue de código dispara un build de 1–2 minutos con `sa-cloudbuild-mdmsync`. Las imágenes quedan en Artifact Registry (unas decenas de MB por servicio).

---

## Cuándo empezaría a costar
Solo con un volumen muy superior al de una demo, por ejemplo miles de sincronizaciones diarias con cambios reales. La Scheduled Query sigue sin horario, así que nada corre por su cuenta.

## Cómo verificar el gasto real
1. Consola de GCP → **Facturación** → **Informes**.
2. Filtra por **Proyecto**: `arl-dtpr-dev-mdm-country-sync`.
3. Agrupa por **Servicio** para ver el desglose exacto.
