-- sq_detect_country_changes
-- Scheduled Query (on-demand). Compara la ingesta más reciente en
-- raw_arl_all_restcountries.country_raw contra el snapshot vigente en
-- ori_ref_country. Registra cada alta/cambio en trx_country_change y
-- actualiza el snapshot. Ambos pasos van en una sola transacción: si falla el
-- MERGE, se deshace también el INSERT y un reintento no duplica los cambios.

BEGIN TRANSACTION;

-- Paso 1: detectar y auditar los cambios (INSERT = país nuevo, UPDATE = país existente modificado)
INSERT INTO `std_arl_all_restcountries.trx_country_change`
  (change_id, country_code, change_type, field_changed, old_value, new_value, detected_at)
SELECT
  GENERATE_UUID() AS change_id,
  R.country_code,
  IF(O.country_code IS NULL, 'INSERT', 'UPDATE') AS change_type,
  CASE
    WHEN O.country_code IS NULL THEN NULL
    WHEN R.name_common IS DISTINCT FROM O.name THEN 'name'
    WHEN R.capital IS DISTINCT FROM O.capital THEN 'capital'
    WHEN R.population IS DISTINCT FROM O.population THEN 'population'
    WHEN R.region IS DISTINCT FROM O.region THEN 'region'
    WHEN R.currency_code IS DISTINCT FROM O.currency_code THEN 'currency_code'
  END AS field_changed,
  TO_JSON_STRING(O) AS old_value,
  TO_JSON_STRING(R) AS new_value,
  CURRENT_TIMESTAMP() AS detected_at
FROM (
  -- última ingesta por país (por si hubo más de una corrida el mismo día)
  SELECT AS VALUE ARRAY_AGG(t ORDER BY t.ingestion_timestamp DESC LIMIT 1)[OFFSET(0)]
  FROM `raw_arl_all_restcountries.country_raw` t
  GROUP BY t.country_code
) R
LEFT JOIN `std_arl_all_restcountries.ori_ref_country` O
  ON R.country_code = O.country_code
WHERE O.country_code IS NULL
   OR R.name_common IS DISTINCT FROM O.name
   OR R.capital IS DISTINCT FROM O.capital
   OR R.population IS DISTINCT FROM O.population
   OR R.region IS DISTINCT FROM O.region
   OR R.currency_code IS DISTINCT FROM O.currency_code;

-- Paso 2: actualizar el snapshot vigente con el estado más reciente
MERGE `std_arl_all_restcountries.ori_ref_country` O
USING (
  SELECT AS VALUE ARRAY_AGG(t ORDER BY t.ingestion_timestamp DESC LIMIT 1)[OFFSET(0)]
  FROM `raw_arl_all_restcountries.country_raw` t
  GROUP BY t.country_code
) R
ON O.country_code = R.country_code
WHEN MATCHED THEN
  UPDATE SET
    name = R.name_common,
    capital = R.capital,
    population = R.population,
    region = R.region,
    currency_code = R.currency_code,
    last_synced_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN
  INSERT (country_code, name, capital, population, region, currency_code, last_synced_at)
  VALUES (R.country_code, R.name_common, R.capital, R.population, R.region, R.currency_code, CURRENT_TIMESTAMP());

COMMIT TRANSACTION;
