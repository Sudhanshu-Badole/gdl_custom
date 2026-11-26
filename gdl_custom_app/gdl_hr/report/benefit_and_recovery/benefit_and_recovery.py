"""Amounts by benefit or recovery across Full and Final Statements."""

import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"label": _("Section"), "fieldname": "section", "fieldtype": "Data", "width": 190},
		{"label": _("Benefit / Recovery"), "fieldname": "component", "fieldtype": "Data", "width": 260},
		{"label": _("Statements"), "fieldname": "statements", "fieldtype": "Int", "width": 100},
		{"label": _("Total Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 150},
	]
	conditions, values = [], {}
	conditions.append("s.docstatus in (0, 1)" if filters.get("include_drafts") else "s.docstatus = 1")
	if filters.get("from_date"):
		conditions.append("s.transaction_date >= %(from_date)s")
		values["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conditions.append("s.transaction_date <= %(to_date)s")
		values["to_date"] = filters["to_date"]
	if filters.get("section"):
		conditions.append("r.custom_section = %(section)s")
		values["section"] = filters["section"]
	data = frappe.db.sql(
		f"""select r.custom_section as section, r.component, count(distinct s.name) as statements, sum(r.amount) as amount
		from `tabFull and Final Outstanding Statement` r
		join `tabFull and Final Statement` s on s.name = r.parent
		where {' and '.join(conditions)} and r.amount > 0
		group by r.custom_section, r.component order by r.custom_section, r.component""",
		values,
		as_dict=True,
	)
	return columns, data
