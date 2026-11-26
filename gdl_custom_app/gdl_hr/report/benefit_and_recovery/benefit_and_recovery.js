frappe.query_reports["Benefit and Recovery"] = {
	filters: [
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date" },
		{ fieldname: "section", label: __("Section"), fieldtype: "Select", options: "\nA. Earned Pay\nB. Separation Benefits\nC. Recoveries" },
		{ fieldname: "include_drafts", label: __("Include Draft Statements"), fieldtype: "Check", default: 0 }
	],
};
