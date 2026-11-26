"""Employees whose nomination is missing, not verified or does not total 100%."""

import frappe
from frappe import _

from gdl_custom_app.gdl_hr.nomination import VALID, get_nomination_status


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 110},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 170},
		{"label": _("Department"), "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 170},
		{"label": _("Nomination Status"), "fieldname": "status", "fieldtype": "Data", "width": 140},
		{"label": _("Nomination"), "fieldname": "nomination", "fieldtype": "Link", "options": "Employee Nomination", "width": 150},
		{"label": _("Separation Request"), "fieldname": "request", "fieldtype": "Link", "options": "Separation Request", "width": 150},
	]
	requests = {
		r.employee: r.name
		for r in frappe.get_all(
			"Separation Request",
			filters={"workflow_state": ["in", ["Pending Supervisor Approval", "Pending CEO Approval", "Approved by CEO", "HR Acknowledged"]]},
			fields=["name", "employee"],
		)
	}
	employee_filters = {"status": "Active"}
	if not filters.get("all_employees"):
		employee_filters = {"name": ["in", list(requests) or [""]]}
	data = []
	for emp in frappe.get_all("Employee", filters=employee_filters, fields=["name", "employee_name", "department"], order_by="employee_name"):
		status = get_nomination_status(emp.name)
		if status == VALID:
			continue
		data.append(
			{
				"employee": emp.name,
				"employee_name": emp.employee_name,
				"department": emp.department,
				"status": status,
				"nomination": frappe.db.exists("Employee Nomination", {"employee": emp.name}),
				"request": requests.get(emp.name),
			}
		)
	return columns, data
