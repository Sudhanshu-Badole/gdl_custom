// Copyright (c) 2026, Sudhanshu Badole and contributors
frappe.query_reports["BTC Reconciliation"] = {
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
		}
	],
};
