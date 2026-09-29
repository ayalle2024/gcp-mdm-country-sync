-- Migración de una tabla trx_crud_action ya existente: agrega las 3 columnas nuevas de auditoría.
-- Las columnas son opcionales (NULL), por lo que las filas anteriores se conservan.
-- Ejecutar ANTES de desplegar la nueva versión de cr-crud-mdm-country-api.
ALTER TABLE `std_arl_all_restcountries.trx_crud_action`
  ADD COLUMN IF NOT EXISTS result  STRING OPTIONS (description = "Resultado: CREATED, UPDATED, NO_CHANGE, DELETED u OK (lecturas)."),
  ADD COLUMN IF NOT EXISTS caller  STRING OPTIONS (description = "Quién llamó al CRUD: 'manual' o el nombre del servicio (ej. cf-update-mdm-country)."),
  ADD COLUMN IF NOT EXISTS payload STRING OPTIONS (description = "Datos enviados en la acción, serializados en JSON.");
