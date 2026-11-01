// Copyright (c) 2026, Sudhanshu Badole and contributors
frappe.query_reports["BTC Movement History"] = {
	filters: [
		{
			"fieldname": "company",
			"label": "Company",
			"fieldtype": "Link",
			"options": "Company",
			"reqd": 1,
			"default": frappe.defaults.get_user_default("Company")
		},
		{
			"fieldname": "item_code",
			"label": "Item Code",
			"fieldtype": "Link",
			"options": "Item"
		},
		{
			"fieldname": "warehouse",
			"label": "Warehouse",
			"fieldtype": "Link",
			"options": "Warehouse"
		},
		{
			"fieldname": "zone",
			"label": "Zone",
			"fieldtype": "Link",
			"options": "Internal Zone"
		},
		{
			"fieldname": "wallet",
			"label": "Wallet",
			"fieldtype": "Link",
			"options": "BTC Wallet"
		},
		{
			"fieldname": "from_date",
			"label": "From Date",
			"fieldtype": "Date"
		},
		{
			"fieldname": "to_date",
			"label": "To Date",
			"fieldtype": "Date"
		}
	],
};
