// Copyright (c) 2026, Sudhanshu Badole and contributors
frappe.query_reports["BTC Restricted Holdings"] = {
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
			"fieldname": "status",
			"label": "Status",
			"fieldtype": "Select",
			"options": "\nTrading\nLoan\nPledged"
		},
		{
			"fieldname": "state",
			"label": "State",
			"fieldtype": "Select",
			"options": "\nActive\nReleased\nExpired\nCancelled"
		}
	],
};
