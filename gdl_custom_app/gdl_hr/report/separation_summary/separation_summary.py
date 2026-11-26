"""Separation requests counted by type and workflow state, with the average notice shortfall."""

import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"label": _("Separation Type"), "fieldname": "separation_type", "fieldtype": "Link", "options": "Separation Type", "width": 220},
		{"label": _("Status"), "fieldname": "workflow_state", "fieldtype": "Data", "width": 200},
		{"label": _("Requests"), "fieldname": "requests", "fieldtype": "Int", "width": 100},
		{"label": _("With Notice Shortfall"), "fieldname": "short", "fieldtype": "Int", "width": 160},
		{"label": _("Average Shortfall (days)"), "fieldname": "avg_shortfall", "fieldtype": "Float", "width": 170},
	]
	conditions, values = ["1=1"], {}
	if filters.get("from_date"):
		conditions.append("resignation_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conditions.append("resignation_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]
	if filters.get("separation_type"):
		conditions.append("separation_type = %(separation_type)s")
		values["separation_type"] = filters["separation_type"]
	data = frappe.db.sql(
		f"""select separation_type, workflow_state, count(*) as requests,
			sum(notice_shortfall_days > 0) as short, avg(notice_shortfall_days) as avg_shortfall
		from `tabSeparation Request` where {' and '.join(conditions)}
		group by separation_type, workflow_state order by separation_type, workflow_state""",
		values,
		as_dict=True,
	)
	return columns, data
