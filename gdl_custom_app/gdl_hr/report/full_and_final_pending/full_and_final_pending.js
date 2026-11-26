frappe.query_reports["Full and Final Pending"] = {
	filters: [
		{ fieldname: "separation_type", label: __("Separation Type"), fieldtype: "Link", options: "Separation Type" }
	],
};
