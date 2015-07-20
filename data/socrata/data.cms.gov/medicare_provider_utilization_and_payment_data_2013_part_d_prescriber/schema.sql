CREATE TABLE "medicare_provider_utilization_and_payment_data_2013_part_d_prescriber" (
	"npi"	text,
	"nppes_provider_last_org_name"	text,
	"nppes_provider_first_name"	text,
	"nppes_provider_city"	text,
	"nppes_provider_state"	text,
	"specialty_desc"	text,
	"description_flag"	text,
	"drug_name"	text,
	"generic_name"	text,
	"bene_count"	real,
	"total_claim_count"	real,
	"total_day_supply"	real,
	"total_drug_cost"	real,
	"bene_count_ge65"	real,
	"bene_count_ge65_redact_flag"	text,
	"total_claim_count_ge65"	real,
	"ge65_redact_flag"	text,
	"total_day_supply_ge65"	real,
	"total_drug_cost_ge65"	real
);