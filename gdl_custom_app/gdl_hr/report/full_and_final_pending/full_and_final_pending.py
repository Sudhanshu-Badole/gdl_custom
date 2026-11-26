"""Approved separations whose Full and Final Statement is not yet submitted, with what is holding each one."""

import frappe
from frappe import _

from gdl_custom_app.gdl_hr.fnf import is_demise, open_clearance_items
from gdl_custom_app.gdl_hr.nomination import get_nomination_status


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"label": _("Request"), "fieldname": "request", "fieldtype": "Link", "options": "Separation Request", "width": 150},
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 110},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 160},
		{"label": _("Separation Type"), "fieldname": "separation_type", "fieldtype": "Data", "width": 170},
		{"label": _("Last Working Date"), "fieldname": "last_working_date", "fieldtype": "Date", "width": 120},
		{"label": _("Exit Interview"), "fieldname": "interview_status", "fieldtype": "Data", "width": 110},
		{"label": _("Open Clearance Items"), "fieldname": "open_clearance", "fieldtype": "Int", "width": 130},
		{"label": _("Nomination"), "fieldname": "nomination", "fieldtype": "Data", "width": 120},
		{"label": _("Statement"), "fieldname": "statement", "fieldtype": "Link", "options": "Full and Final Statement", "width": 150},
		{"label": _("Waiting For"), "fieldname": "waiting_for", "fieldtype": "Data", "width": 260},
	]
	request_filters = {"workflow_state": ["in", ["Approved by CEO", "HR Acknowledged"]]}
	if filters.get("separation_type"):
		request_filters["separation_type"] = filters["separation_type"]
	data = []
	for req in frappe.get_all(
		"Separation Request",
		filters=request_filters,
		fields=["name", "employee", "employee_name", "separation_type", "last_working_date", "exit_interview", "employee_separation", "workflow_state"],
		order_by="last_working_date",
	):
		statement = frappe.db.get_value("Full and Final Statement", {"employee": req.employee, "docstatus": ["!=", 2]}, ["name", "docstatus"], as_dict=True)
		if statement and statement.docstatus == 1:
			continue
		demise = is_demise(req.separation_type)
		interview = req.exit_interview and frappe.db.get_value("Exit Interview", req.exit_interview, "status")
		open_items = open_clearance_items(req.employee_separation) if req.employee_separation else []
		waiting = []
		if not demise and interview != "Completed":
			waiting.append(_("Exit interview"))
		if req.workflow_state != "HR Acknowledged":
			waiting.append(_("HR acknowledgement"))
		elif not req.employee_separation or open_items:
			waiting.append(_("Clearance"))
		if not statement:
			waiting.append(_("Statement not prepared"))
		else:
			waiting.append(_("Statement in draft"))
		data.append(
			{
				"request": req.name,
				"employee": req.employee,
				"employee_name": req.employee_name,
				"separation_type": req.separation_type,
				"last_working_date": req.last_working_date,
				"interview_status": _("Not needed") if demise else (interview or _("Not created")),
				"open_clearance": len(open_items) if req.employee_separation else None,
				"nomination": get_nomination_status(req.employee),
				"statement": statement.name if statement else None,
				"waiting_for": ", ".join(waiting),
			}
		)
	return columns, data
