frappe.query_reports["Exit Interview Answers"] = {
	filters: [
		{ fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
		{ fieldname: "part", label: __("Part"), fieldtype: "Data" },
	],
};
