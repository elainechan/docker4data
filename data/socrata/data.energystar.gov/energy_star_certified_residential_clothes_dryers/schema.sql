CREATE TABLE "energy_star_certified_residential_clothes_dryers" (
	"pd_id"	real,
	"brand_name"	text,
	"model_name"	text,
	"model_number"	text,
	"additional_model_information"	text,
	"upc"	text,
	"type"	text,
	"drum_capacity_cu_ft"	real,
	"height_inches"	real,
	"width_inches"	real,
	"depth_inches"	real,
	"combined_energy_factor_cef"	real,
	"estimated_annual_energy_use_kwh_yr"	real,
	"estimated_energy_test_cycle_time_min"	real,
	"energy_test_cycle_information"	text,
	"additional_dryer_features"	text,
	"vented_or_ventless"	text,
	"connected"	text,
	"paired_energy_star_clothes_washer_available"	text,
	"paired_energy_star_clothes_washer_energy_star_model_identifier"	text,
	"date_available_on_market"	timestamp,
	"date_qualified"	timestamp,
	"markets"	text,
	"energy_star_model_identifier"	text
);