"""All submitted exit questionnaire answers, one row per answer. Confidential to HR roles (report roles)."""

import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 110},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 160},
		{"label": _("Response"), "fieldname": "response", "fieldtype": "Link", "options": "Exit Interview Response", "width": 150},
		{"label": _("Part"), "fieldname": "part", "fieldtype": "Data", "width": 190},
		{"label": _("Question"), "fieldname": "question", "fieldtype": "Data", "width": 360},
		{"label": _("Answer"), "fieldname": "answer", "fieldtype": "Data", "width": 280},
	]


def get_data(filters):
	conditions, values = ["r.docstatus = 1"], {}
	if filters.get("employee"):
		conditions.append("r.employee = %(employee)s")
		values["employee"] = filters["employee"]
	if filters.get("part"):
		conditions.append("a.part like %(part)s")
		values["part"] = f"%{filters['part']}%"
	return frappe.db.sql(
		f"""select r.employee, r.employee_name, r.name as response, a.part, a.question, a.answer
		from `tabExit Interview Answer` a
		join `tabExit Interview Response` r on r.name = a.parent and a.parenttype = 'Exit Interview Response'
		where {' and '.join(conditions)}
		order by r.employee, r.name, a.idx""",
		values,
		as_dict=True,
	)
