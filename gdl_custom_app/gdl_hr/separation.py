"""Employee Separation extension: create it from an approved request, keep the notice tracker, and
require the clearance sign-off attachment before the last clearance task is completed."""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, nowdate

CLEARANCE_TEMPLATE = "GDL Clearance"
DEMISE_ACTIVITY = "Clearance signed off outside the system (demise): upload the sign-off document"

# Activities whose owner is a person on the employee record, not a role.
SUPERVISOR_ACTIVITIES = (
	"Hand over charge, files and records to the supervisor",
	"Complete the performance evaluation for the period served (pro-rated PBVP)",
)
REVIEWER_ACTIVITIES = ("Reviewer endorsement of the handover",)

# (activity name, role, begin_on days, duration days). Role is blank for supervisor/reviewer items.
CLEARANCE_ACTIVITIES = (
	(SUPERVISOR_ACTIVITIES[0], "", 0, 10),
	(REVIEWER_ACTIVITIES[0], "", 0, 12),
	("Return keys, laptop, equipment, supplies, records and identification card", "ICT", 0, 14),
	("Return company fixed assets issued by GDL to HRA", "HRA", 0, 14),
	("Clear all dues and advances with Accounts (salary advance, travel advance, other dues)", "Accounts User", 0, 14),
	("Provide documents for post-retirement benefits (NPPF forms, GIS, nomination, bank details, CID copy)", "HRA", 0, 14),
	("Any other clearance (corporate accommodation, training or study undertaking status)", "HRA", 0, 14),
	(SUPERVISOR_ACTIVITIES[1], "", 0, 14),
	("Disable ICT access and email; recover access cards", "ICT", 0, 14),
)


def get_clearance_template():
	"""The template is named by series (HR-EMP-STP-#####); find it by title."""
	return frappe.db.get_value("Employee Separation Template", {"title": CLEARANCE_TEMPLATE})


def create_employee_separation(request):
	"""Open the Employee Separation (draft) with the clearance checklist from an HR-acknowledged request."""
	skip_clearance = frappe.db.get_value("Separation Type", request.separation_type, "skip_employee_clearance")
	supervisor = request.supervisor_user
	reviewer = frappe.db.get_value("Employee", request.reviewer, "user_id") if request.reviewer else None

	es = frappe.new_doc("Employee Separation")
	es.employee = request.employee
	es.boarding_begins_on = request.resignation_date
	es.resignation_letter_date = request.resignation_date
	template_name = get_clearance_template()
	es.employee_separation_template = template_name
	es.notify_users_by_email = 0
	es.custom_separation_request = request.name

	if skip_clearance:
		es.append("activities", {"activity_name": DEMISE_ACTIVITY, "role": "HRA", "begin_on": 0, "duration": 30})
	else:
		template = frappe.get_doc("Employee Separation Template", template_name)
		for row in template.activities:
			activity = {
				"activity_name": row.activity_name,
				"role": row.role,
				"begin_on": row.begin_on,
				"duration": row.duration,
				"task_weight": row.task_weight,
				"description": row.description,
			}
			if row.activity_name in SUPERVISOR_ACTIVITIES and supervisor:
				activity.update(user=supervisor, role=None)
			elif row.activity_name in REVIEWER_ACTIVITIES and reviewer:
				activity.update(user=reviewer, role=None)
			elif not row.role:
				activity["role"] = "HRA"  # no supervisor/reviewer user on file: HRA follows up
			es.append("activities", activity)

	es.insert(ignore_permissions=True)
	return es.name


def refresh_notice_tracker(doc, method=None):
	"""Employee Separation validate hook: pull the notice figures from the linked request."""
	if not doc.get("custom_separation_request"):
		return
	req = frappe.db.get_value(
		"Separation Request",
		doc.custom_separation_request,
		["separation_type", "resignation_date", "last_working_date", "notice_days"],
		as_dict=True,
	)
	if not req:
		return
	doc.custom_separation_type = req.separation_type
	doc.custom_notice_days = req.notice_days
	today = getdate(nowdate())
	last = getdate(req.last_working_date)
	start = getdate(req.resignation_date)
	served = max(0, date_diff(min(today, last), start))
	doc.custom_notice_served_days = served
	doc.custom_notice_remaining_days = max(0, date_diff(last, today))
	doc.custom_notice_shortfall_days = max(0, flt(req.notice_days) - date_diff(last, start))


def require_clearance_attachment(doc, method=None):
	"""Task validate hook: the last open clearance task cannot be completed without the sign-off file."""
	if doc.status != "Completed" or not doc.project:
		return
	es = frappe.db.get_value(
		"Employee Separation", {"project": doc.project}, ["name", "custom_clearance_attachment"], as_dict=True
	)
	if not es or es.custom_clearance_attachment:
		return
	tasks = frappe.get_all(
		"Employee Boarding Activity",
		filters={"parent": es.name, "parenttype": "Employee Separation", "task": ["is", "set"]},
		pluck="task",
	)
	if doc.name not in tasks:
		return
	others = [t for t in tasks if t != doc.name]
	open_tasks = frappe.db.count("Task", {"name": ["in", others], "status": ["!=", "Completed"]}) if others else 0
	if not open_tasks:
		frappe.throw(
			_("Attach the clearance sign-off document on Employee Separation {0} before completing the last clearance item.").format(
				es.name
			)
		)
