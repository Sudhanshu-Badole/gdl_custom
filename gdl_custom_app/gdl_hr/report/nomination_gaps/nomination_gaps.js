frappe.query_reports["Nomination Gaps"] = {
	filters: [
		{ fieldname: "all_employees", label: __("All Active Employees (not only those separating)"), fieldtype: "Check", default: 0 }
	],
};
