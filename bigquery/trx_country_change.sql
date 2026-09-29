CREATE TABLE IF NOT EXISTS `std_arl_all_restcountries.trx_country_change` (
  change_id       STRING NOT NULL OPTIONS (description = "Identificador único del cambio detectado (UUID)."),
  country_code    STRING NOT NULL OPTIONS (description = "Llave foránea hacia ori_ref_country.country_code."),
  change_type     STRING NOT NULL OPTIONS (description = "Tipo de cambio detectado: INSERT (país nuevo) o UPDATE (país existente modificado)."),
  field_changed   STRING OPTIONS (description = "Nombre del primer campo detectado como distinto respecto al snapshot anterior."),
  old_value       STRING OPTIONS (description = "Estado anterior del registro completo, serializado en JSON."),
  new_value       STRING OPTIONS (description = "Estado nuevo del registro completo, serializado en JSON."),
  detected_at     TIMESTAMP NOT NULL OPTIONS (description = "Timestamp UTC en que se detectó el cambio. Columna de particionamiento.")
)
PARTITION BY DATE(detected_at)
CLUSTER BY country_code
OPTIONS (description = "Tabla transaccional: un registro por cada cambio detectado en un país, comparando la ingesta del día contra ori_ref_country.");
