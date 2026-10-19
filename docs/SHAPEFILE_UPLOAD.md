# Shapefile (.zip) upload

Institutions may send the loan and collateral data as a **Shapefile in a ZIP** (the Concept Note's upload panel), besides Excel and CSV. The limit is **50 MB** and 100,000 rows. The file goes through exactly the same validation as an Excel file (regions, districts, wards, coordinates inside the district, amounts, dates, duplicates).

## How to prepare it (GIS software, e.g. QGIS)

1. One layer of **points**: each point is where the loan is invested. Lines and polygons are refused.
2. Coordinates in **WGS 84 (EPSG:4326)**, degrees. A projected system (metres) is refused with a message that says how to export again.
3. The attribute table (.dbf) holds the other columns, with the names below. A DBF name has at most 10 characters, so the names are short. The full template names are accepted too, when the tool keeps them.
4. Zip `.shp`, `.shx`, `.dbf` and `.prj` (and `.cpg` if the text is not UTF-8) together, **only** these, one layer per ZIP.
5. The point becomes the loan's latitude and longitude; `loan_lat` / `loan_lon` in the table are used only for a record that has no point. The collateral coordinates (`coll_lat`, `coll_lon`) are read from the table.

## Column names in the attribute table

| Table column | Template column | Field |
|---|---|---|
| `cust_id` | Customer Identification Number | `customer_id` |
| `br_code` | Branch Code | `branch_code` |
| `br_name` | Branch name | `branch_name` |
| `client_typ` | Client Type | `client_type` |
| `biz_size` | Size of the business | `business_size` |
| `turnover` | Annual turn-over of the borrower | `annual_turnover_tzs` |
| `loan_id` | Loan number | `loan_id` |
| `disb_date` | Disbursement Date (Date/Month/Year) | `disbursement_date` |
| `mat_date` | Maturity Date (Date/Month/Year) | `maturity_date` |
| `currency` | Currency | `currency` |
| `loan_amt` | TZS Disbursed Amount | `loan_amount_tzs` |
| `out_princ` | TZS Outstanding Principal Amount | `outstanding_principal_tzs` |
| `int_rate` | Annual Interest Rate | `annual_interest_rate` |
| `loan_type` | loan Type/ General Category | `loan_type` |
| `loan_econ` | Loan Economic Activity | `loan_economic_activity` |
| `loan_purp` | Purpose of the loan | `loan_purpose` |
| `asset_cls` | Asset Classification Category | `asset_classification` |
| `region` | Location of invested loan (Region) | `region` |
| `district` | Location of invested loan (District) | `district` |
| `ward` | Location of invested loan (Ward) | `ward` |
| `village` | Location of invested loan (Street/village) | `village` |
| `loan_lat` | Invested Loan Geographical coordinates (Latitude) | `loan_latitude` |
| `loan_lon` | Invested Loan Geographical coordinates (Longitude) | `loan_longitude` |
| `coll_type` | Collateral Pledged | `collateral_type` |
| `coll_date` | Collateral Pledged Date | `collateral_pledged_date` |
| `coll_value` | TZS Market value of the collateral | `collateral_value_tzs` |
| `coll_fsv` | TZS Forced Sale Value of the collateral | `collateral_forced_sale_value_tzs` |
| `coll_econ` | Collateral Economic activity | `collateral_economic_activity` |
| `coll_reg` | Location of the collateral (Region) | `collateral_region` |
| `coll_dist` | Location of the collateral (District) | `collateral_district` |
| `coll_ward` | Location of the collateral (Ward) | `collateral_ward` |
| `coll_vill` | Location of the collateral (Street) | `collateral_village` |
| `coll_lat` | Collateral Geographical Coordinates (Latitude) | `collateral_latitude` |
| `coll_lon` | Collateral Geographical Coordinates (Longitude) | `collateral_longitude` |
| `ins_cover` | Insurance coverage of the collateral against climate risks | `insurance_coverage` |
| `ins_type` | Type of insurance policy | `insurance_policy_type` |
| `ins_prov` | Name of insurance provider | `insurance_provider_name` |
| `ins_value` | Value of Collateral Protected | `insurance_value_protected_tzs` |

## What is refused, and why (security)

Nothing in the ZIP is ever written to disk: every part is read in memory, so a file name such as `../../x` cannot write anywhere (such names are refused). Refused: any file that is not part of a shapefile (an `.exe`, a ZIP inside the ZIP), a password-protected ZIP, more than 20 parts, a part over 150 MB or all parts over 200 MB once unpacked, an unusual compression ratio (a "ZIP bomb"; the sizes written in the ZIP are not believed, the reading stops at the limit), more than one layer, a layer that is not points, and a damaged or inconsistent `.shp`/`.dbf`. More rows than the limit are refused from the table header, before a record is read. No outside library is used (the Python standard library only), so nothing new is added to the system to maintain or to audit.

The original ZIP is kept like any uploaded file and can be downloaded again from the submission.

## Limits

* Loan and collateral upload (Excel, CSV, Shapefile ZIP): `MAX_UPLOAD_SIZE_MB` = 50, `MAX_UPLOAD_ROWS` = 100,000. nginx allows 55 MB so the application gives the clear message.
* Climate files (staff upload, TMA/PMO sending): `MAX_CLIMATE_UPLOAD_SIZE_MB` = 20, unchanged.
* A 50 MB upload at 100,000 rows needs about 0.5 GB of application memory (`LOAD_TESTING.md`); a ZIP is unpacked in memory, at most 200 MB. A load test on staging with a 50 MB ZIP is still to be done (Section A, item 6).
