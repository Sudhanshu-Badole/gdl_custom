"""Daily closure: on the last working day set the Employee to Left, close the leave ledger, disable
the User and send the closing status to the personal email. Idempotent."""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate


def close_due_separations():
	"""Scheduler entry point (daily)."""
	today = getdate(nowdate())
	for name in frappe.get_all(
		"Separation Request",
		filters={"workflow_state": "HR Acknowledged", "last_working_date": ["<=", today]},
		pluck="name",
	):
		try:
			close_separation(name)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Separation closure failed: {name}")


def close_separation(request_name):
	"""Returns True when the employee was closed now, False when already Left."""
	req = frappe.get_doc("Separation Request", request_name)
	employee = frappe.get_doc("Employee", req.employee)
	if employee.status == "Left":
		return False

	employee.status = "Left"
	employee.relieving_date = req.last_working_date
	employee.resignation_letter_date = employee.resignation_letter_date or req.resignation_date
	employee.reason_for_leaving = "{0}: {1}".format(req.separation_type, req.reason_for_leaving or "")[:140]
	employee.save(ignore_permissions=True)

	close_leave_ledger(req.employee, req.last_working_date)
	disable_user(employee.user_id)
	try:
		send_closure_email(req)
	except Exception:  # a mail problem (e.g. no outgoing account) must not undo the closure
		frappe.log_error(title=f"Separation closure email failed: {req.name}")
	return True


def close_leave_ledger(employee, last_working_date):
	"""Stop leave allocations at the last working day, in the allocation and its ledger entries."""
	allocations = frappe.get_all(
		"Leave Allocation",
		filters={
			"employee": employee,
			"docstatus": 1,
			"from_date": ["<=", last_working_date],
			"to_date": [">", last_working_date],
		},
		pluck="name",
	)
	for name in allocations:
		frappe.db.set_value("Leave Allocation", name, "to_date", last_working_date, update_modified=False)
		frappe.db.sql(
			"""update `tabLeave Ledger Entry` set to_date = %s
			where transaction_type = 'Leave Allocation' and transaction_name = %s
			and to_date > %s and docstatus = 1""",
			(last_working_date, name, last_working_date),
		)


def disable_user(user):
	if not user or user in ("Administrator", "Guest") or not frappe.db.exists("User", user):
		return
	if frappe.db.get_value("User", user, "enabled"):
		frappe.db.set_value("User", user, "enabled", 0)
		frappe.sessions.clear_sessions(user, force=True)


def send_closure_email(req):
	if not req.personal_email:
		return
	frappe.sendmail(
		recipients=[req.personal_email],
		subject=_("Separation completed: {0}").format(req.employee_name),
		message=_(
			"Dear {0},<br><br>Your separation from GreenDigital Limited is complete. "
			"Your employment status is now <b>Left</b> with the relieving date {1}. "
			"System access has been disabled.<br><br>Human Resources"
		).format(req.employee_name, frappe.format(req.last_working_date, {"fieldtype": "Date"})),
		reference_doctype=req.doctype,
		reference_name=req.name,
	)
