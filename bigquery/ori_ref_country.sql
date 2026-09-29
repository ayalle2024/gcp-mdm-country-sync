CREATE SCHEMA IF NOT EXISTS `std_arl_all_restcountries`
  OPTIONS (
    location = 'US',
    description = "Capa estandarizada: snapshot vigente, auditoría de cambios y auditoría del CRUD para el maestro de países."
  );

CREATE TABLE IF NOT EXISTS `std_arl_all_restcountries.ori_ref_country` (
  country_code    STRING NOT NULL OPTIONS (description = "Llave primaria: código ISO de 3 letras del país."),
  name            STRING NOT NULL OPTIONS (description = "Nombre común del país."),
  capital         STRING OPTIONS (description = "Capital del país."),
  population      INT64 OPTIONS (description = "Población total del país, según la última sincronización."),
  region          STRING OPTIONS (description = "Región geográfica del país."),
  currency_code   STRING OPTIONS (description = "Código de moneda principal del país."),
  last_synced_at  TIMESTAMP NOT NULL OPTIONS (description = "Timestamp UTC de la última vez que este registro se actualizó desde la capa raw.")
)
OPTIONS (description = "Dato de referencia transversal (no propio del negocio): snapshot vigente de cada país, usado tanto para detectar cambios como para consulta directa del estado actual.");
