"""Idempotent setup for the Employee Separation process: roles, masters, custom fields, clearance
template, approval workflow and notifications. Run from the hr_separation_setup patch."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from gdl_custom_app.gdl_hr.separation import CLEARANCE_ACTIVITIES, CLEARANCE_TEMPLATE, get_clearance_template

DOCTYPE = "Separation Request"
WORKFLOW = "Separation Request Approval"

ROLES = ("CEO", "HRA", "ICT")

SEPARATION_TYPES = (
	("Superannuation", 0),
	("Voluntary resignation", 0),
	("Retrenchment", 0),
	("Compulsory retirement", 0),
	("Termination (disciplinary)", 0),
	("Termination of contract", 0),
	("Expiry of contract", 0),
	("Demise", 1),
)

CUSTOM_FIELDS = {
	"Employee": [
		{"fieldname": "custom_reviewer", "label": "Reviewer", "fieldtype": "Link", "options": "Employee", "insert_after": "reports_to"},
		{"fieldname": "custom_exit_obligations_section", "label": "Exit Obligations", "fieldtype": "Section Break", "insert_after": "reason_for_leaving"},
		{"fieldname": "custom_under_investigation", "label": "Under Investigation", "fieldtype": "Check", "insert_after": "custom_exit_obligations_section", "description": "Set by HR. Blocks the employee from submitting a separation request."},
		{"fieldname": "custom_training_study_undertaking", "label": "Training / Study Undertaking", "fieldtype": "Select", "options": "\nNone\nSTTP\nLTTP\nStudy Leave", "insert_after": "custom_under_investigation", "description": "Open training or study leave undertaking, set by HR."},
	],
	"Employee Separation": [
		{"fieldname": "custom_separation_request", "label": "Separation Request", "fieldtype": "Link", "options": "Separation Request", "insert_after": "employee_separation_template", "read_only": 1, "no_copy": 1},
		{"fieldname": "custom_separation_type", "label": "Separation Type", "fieldtype": "Link", "options": "Separation Type", "insert_after": "custom_separation_request", "read_only": 1},
		{"fieldname": "custom_notice_section", "label": "Notice Period Tracker", "fieldtype": "Section Break", "insert_after": "activities"},
		{"fieldname": "custom_notice_days", "label": "Notice Period (Days)", "fieldtype": "Int", "insert_after": "custom_notice_section", "read_only": 1},
		{"fieldname": "custom_notice_served_days", "label": "Days Served", "fieldtype": "Int", "insert_after": "custom_notice_days", "read_only": 1},
		{"fieldname": "custom_notice_column", "fieldtype": "Column Break", "insert_after": "custom_notice_served_days"},
		{"fieldname": "custom_notice_remaining_days", "label": "Days Remaining", "fieldtype": "Int", "insert_after": "custom_notice_column", "read_only": 1},
		{"fieldname": "custom_notice_shortfall_days", "label": "Shortfall (Days)", "fieldtype": "Int", "insert_after": "custom_notice_remaining_days", "read_only": 1},
		{"fieldname": "custom_clearance_section", "label": "Clearance Sign-off", "fieldtype": "Section Break", "insert_after": "custom_notice_shortfall_days"},
		{"fieldname": "custom_clearance_attachment", "label": "Clearance Sign-off Document", "fieldtype": "Attach", "insert_after": "custom_clearance_section", "allow_on_submit": 1, "description": "One document holding every clearance sign-off. Required before the last clearance item is completed."},
	],
}

# (state, doc_status, allow_edit role, style)
STATES = (
	("Draft", 0, "Employee", "Warning"),
	("Pending Supervisor Approval", 0, "Employee", "Primary"),
	("Rejected by Supervisor", 0, "Employee", "Danger"),
	("Pending CEO Approval", 0, "CEO", "Primary"),
	("Rejected by CEO", 0, "Employee", "Danger"),
	("Withheld by CEO", 0, "CEO", "Danger"),
	("Withdrawn", 0, "Employee", "Inverse"),
	("Approved by CEO", 0, "HR Manager", "Success"),
	("HR Acknowledged", 0, "HR Manager", "Success"),
)

SUP = "doc.supervisor_user == frappe.session.user"
OWN = "doc.owner == frappe.session.user"

# (state, action, next state, role, condition)
TRANSITIONS = (
	("Draft", "Submit for Approval", "Pending Supervisor Approval", "Employee", OWN),
	("Draft", "Submit for Approval", "Pending Supervisor Approval", "HR Manager", None),
	("Draft", "Withdraw", "Withdrawn", "Employee", OWN),
	("Pending Supervisor Approval", "Approve", "Pending CEO Approval", "Employee", SUP),
	("Pending Supervisor Approval", "Reject", "Rejected by Supervisor", "Employee", SUP),
	("Rejected by Supervisor", "Amend and Resubmit", "Draft", "Employee", OWN),
	("Rejected by Supervisor", "Withdraw", "Withdrawn", "Employee", OWN),
	("Pending CEO Approval", "Approve", "Approved by CEO", "CEO", None),
	("Pending CEO Approval", "Reject", "Rejected by CEO", "CEO", None),
	("Pending CEO Approval", "Withhold", "Withheld by CEO", "CEO", None),
	("Rejected by CEO", "Amend and Resubmit", "Draft", "Employee", OWN),
	("Rejected by CEO", "Withdraw", "Withdrawn", "Employee", OWN),
	("Approved by CEO", "Acknowledge", "HR Acknowledged", "HR Manager", None),
)

LINK = "<p><a href=\"{{ frappe.utils.get_url_to_form(doc.doctype, doc.name) }}\">{{ doc.name }}</a></p>"
SUMMARY = (
	"<p>Employee: {{ doc.employee_name }} ({{ doc.employee }})<br>"
	"Separation type: {{ doc.separation_type }}<br>"
	"Resignation date: {{ frappe.format(doc.resignation_date, {'fieldtype': 'Date'}) }}<br>"
	"Last working date: {{ frappe.format(doc.last_working_date, {'fieldtype': 'Date'}) }}</p>"
)
REASON = "{% if doc.decision_reason %}<p>Reason: {{ doc.decision_reason }}</p>{% endif %}"

# (name, subject, state, channel, document fields, roles, intro)
NOTIFICATIONS = (
	("Separation Request - Supervisor (Email)", "Separation request {{ doc.name }} awaits your approval", "Pending Supervisor Approval", "Email", ["supervisor_user"], [], "A separation request needs your review."),
	("Separation Request - Supervisor (Alert)", "Separation request {{ doc.name }} awaits your approval", "Pending Supervisor Approval", "System Notification", ["supervisor_user"], [], "A separation request needs your review."),
	("Separation Request - Rejected by Supervisor", "Separation request {{ doc.name }} was rejected by your supervisor", "Rejected by Supervisor", "Email", ["employee_user", "personal_email"], [], "Your supervisor rejected the request. You can amend and resubmit, or withdraw it."),
	("Separation Request - CEO", "Separation request {{ doc.name }} awaits CEO approval", "Pending CEO Approval", "Email", [], ["CEO", "HR Manager"], "The supervisor approved this separation request. HR is copied for visibility."),
	("Separation Request - Rejected by CEO", "Separation request {{ doc.name }} was rejected by the CEO", "Rejected by CEO", "Email", ["employee_user", "personal_email", "supervisor_user"], [], "The CEO rejected the request."),
	("Separation Request - Withheld by CEO", "Separation request {{ doc.name }} was withheld by the CEO", "Withheld by CEO", "Email", ["employee_user", "personal_email", "supervisor_user"], [], "The CEO withheld the request. It is closed."),
	("Separation Request - Approved", "Separation request {{ doc.name }} approved by the CEO", "Approved by CEO", "Email", ["employee_user", "personal_email", "supervisor_user"], ["HR Manager"], "The CEO approved the request. The resignation date and last working day are now fixed and HR will open the separation record."),
)


def execute():
	create_roles()
	create_separation_types()
	frappe.db.commit()  # custom fields reload meta; the doctype must exist first
	create_custom_fields(CUSTOM_FIELDS, update=True)
	create_clearance_template()
	create_workflow()
	create_notifications()
	frappe.clear_cache()


def create_roles():
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)


def create_separation_types():
	for name, skip in SEPARATION_TYPES:
		if not frappe.db.exists("Separation Type", name):
			frappe.get_doc({"doctype": "Separation Type", "type_name": name, "skip_employee_clearance": skip}).insert(
				ignore_permissions=True
			)


def create_clearance_template():
	name = get_clearance_template()
	if name:
		doc = frappe.get_doc("Employee Separation Template", name)
		doc.set("activities", [])
	else:
		doc = frappe.new_doc("Employee Separation Template")
		doc.title = CLEARANCE_TEMPLATE
	for name, role, begin_on, duration in CLEARANCE_ACTIVITIES:
		doc.append("activities", {"activity_name": name, "role": role or None, "begin_on": begin_on, "duration": duration})
	doc.save(ignore_permissions=True)


def create_workflow():
	for state, _status, _role, style in STATES:
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": state, "style": style}).insert(
				ignore_permissions=True
			)
	for action in {t[1] for t in TRANSITIONS}:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert(
				ignore_permissions=True
			)

	if frappe.db.exists("Workflow", WORKFLOW):
		wf = frappe.get_doc("Workflow", WORKFLOW)
		wf.set("states", [])
		wf.set("transitions", [])
	else:
		wf = frappe.new_doc("Workflow")
		wf.workflow_name = WORKFLOW
	wf.document_type = DOCTYPE
	wf.workflow_state_field = "workflow_state"
	wf.is_active = 1
	wf.send_email_alert = 0
	for state, status, role, _style in STATES:
		wf.append("states", {"state": state, "doc_status": str(status), "allow_edit": role})
	for state, action, next_state, role, condition in TRANSITIONS:
		wf.append(
			"transitions",
			{
				"state": state,
				"action": action,
				"next_state": next_state,
				"allowed": role,
				"condition": condition,
				"allow_self_approval": 1,
			},
		)
	wf.save(ignore_permissions=True)


def create_notifications():
	for name, subject, state, channel, fields, roles, intro in NOTIFICATIONS:
		doc = frappe.get_doc("Notification", name) if frappe.db.exists("Notification", name) else frappe.new_doc("Notification")
		doc.name = name
		doc.update(
			{
				"subject": subject,
				"document_type": DOCTYPE,
				"event": "Value Change",
				"value_changed": "workflow_state",
				"condition": f'doc.workflow_state == "{state}"',
				"channel": channel,
				"enabled": 1,
				"message": f"<p>{intro}</p>{SUMMARY}{REASON}{LINK}",
			}
		)
		doc.set("recipients", [])
		for field in fields:
			doc.append("recipients", {"receiver_by_document_field": field})
		for role in roles:
			doc.append("recipients", {"receiver_by_role": role})
		doc.save(ignore_permissions=True)
