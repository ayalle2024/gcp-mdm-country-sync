CREATE TABLE IF NOT EXISTS `std_arl_all_restcountries.trx_crud_action` (
  action_id      STRING NOT NULL OPTIONS (description = "Identificador único de la acción (UUID)."),
  action_type    STRING NOT NULL OPTIONS (description = "Tipo de acción CRUD: CREATE, READ, UPDATE o DELETE."),
  country_code   STRING OPTIONS (description = "País afectado por la acción, cuando aplica (READ de listado completo puede venir vacío)."),
  performed_at   TIMESTAMP NOT NULL OPTIONS (description = "Timestamp UTC en que se ejecutó la acción. Columna de particionamiento."),
  source         STRING NOT NULL OPTIONS (description = "Nombre del servicio que originó la acción (ej. cr-crud-mdm-country-api)."),
  result         STRING OPTIONS (description = "Resultado: CREATED, UPDATED, NO_CHANGE, DELETED u OK (lecturas)."),
  caller         STRING OPTIONS (description = "Quién llamó al CRUD: 'manual' o el nombre del servicio (ej. cf-update-mdm-country)."),
  payload        STRING OPTIONS (description = "Datos enviados en la acción, serializados en JSON.")
)
PARTITION BY DATE(performed_at)
CLUSTER BY country_code
OPTIONS (description = "Tabla transaccional: un registro por cada acción ejecutada contra la API CRUD del maestro de países, tanto manuales como las que envía cf-update-mdm-country.");
