frappe.query_reports["Separation Summary"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date" },
		{ fieldname: "separation_type", label: __("Separation Type"), fieldtype: "Link", options: "Separation Type" }
	],
};
