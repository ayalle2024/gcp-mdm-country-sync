CREATE SCHEMA IF NOT EXISTS `raw_arl_all_restcountries`
  OPTIONS (
    location = 'US',
    description = "Capa raw: espejo de la respuesta de la API REST Countries, sin limpieza ni reglas de negocio."
  );

CREATE TABLE IF NOT EXISTS `raw_arl_all_restcountries.country_raw` (
  country_code         STRING NOT NULL OPTIONS (description = "Código ISO de 3 letras del país (cca3 en la fuente)."),
  name_common           STRING NOT NULL OPTIONS (description = "Nombre común del país (name.common en la fuente)."),
  capital                STRING OPTIONS (description = "Capital del país (primer elemento del arreglo capital[] de la fuente)."),
  population              INT64 OPTIONS (description = "Población total del país."),
  region                  STRING OPTIONS (description = "Región geográfica del país según la fuente."),
  currency_code           STRING OPTIONS (description = "Código de la primera moneda listada en currencies de la fuente."),
  ingestion_timestamp      TIMESTAMP NOT NULL OPTIONS (description = "Timestamp UTC en que el servicio de ingesta trajo este registro. Columna de particionamiento.")
)
PARTITION BY DATE(ingestion_timestamp)
CLUSTER BY country_code
OPTIONS (description = "Tabla raw: una fila por país por cada ejecución de ingesta, campos tal como los devuelve REST Countries. Sin validación aplicada.");
