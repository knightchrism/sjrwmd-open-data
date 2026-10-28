# Data license and disclaimer

The **code** in this repository is MIT licensed (see `LICENSE`). The **data** is not covered by that license.

## Source
All data is retrieved from the St. Johns River Water Management District's (SJRWMD) public ArcGIS Online services
(`https://services.arcgis.com/s8wtJX9suxFen6TA/ArcGIS/rest/services`) and its open data portal
(`https://data-floridaswater.opendata.arcgis.com`).

## Status
SJRWMD records are public records under Florida's public records law (Chapter 119, Florida Statutes).
Item-specific terms published on the SJRWMD open data portal take precedence; check each item's license field.

## Credit
Please credit: **"Source: St. Johns River Water Management District (SJRWMD). Retrieved <date> via the unofficial sjrwmd-open-data mirror."**

## Disclaimer
This is an **unofficial** mirror. It is not produced, endorsed or maintained by SJRWMD. Data may be out of date, transformed
(reprojected to EPSG:3086, invalid rings repaired with `ST_MakeValid` and flagged in `_geom_repaired`), or incomplete.
SJRWMD's own liability disclaimer applies: https://www.sjrwmd.com/disclaimer/

THE DATA IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING ACCURACY, COMPLETENESS OR FITNESS
FOR A PARTICULAR PURPOSE. It is not suitable for legal, survey, engineering or regulatory determinations. Always confirm
with SJRWMD (https://www.sjrwmd.com) and the authoritative permit records.
