"""Exit Interview extension: create it when the CEO approves a request, give the employee the Annexure 1
questionnaire when HR schedules it, and only let HR complete it once the employee has answered."""

import frappe
from frappe import _
from frappe.utils import date_diff, get_url_to_form, getdate, nowdate

TEMPLATE_NAME = "GDL Exit Interview"
SERVICE_QUESTION = "How long have you worked in our company?"
TYPE_QUESTION = "Resignation Type"
TYPE_ANSWERS = {"Voluntary resignation": "Voluntary Resignation", "Superannuation": "Superannuation"}

# (upper bound in months, band). Anything longer is "more than 10 years".
SERVICE_BANDS = (
	(6, "Less than 6 months"),
	(12, "6 months - 1 year"),
	(24, "1-2 years"),
	(48, "2-4 years"),
	(72, "4-6 years"),
	(120, "6-10 years"),
)
LONGEST_BAND = "more than 10 years"


def service_band(date_of_joining, end_date=None):
	"""Years-of-service answer for Part I, from the joining date to the relieving date (or today)."""
	if not date_of_joining:
		return None
	months = date_diff(getdate(end_date or nowdate()), getdate(date_of_joining)) / 30.4375
	for limit, band in SERVICE_BANDS:
		if months < limit:
			return band
	return LONGEST_BAND


def create_exit_interview(request):
	"""Open the Exit Interview (Pending) for an approved request. Returns its name, or None for a demise."""
	if frappe.db.get_value("Separation Type", request.separation_type, "skip_employee_clearance"):
		return None  # demise: the employee cannot be interviewed
	existing = frappe.db.exists("Exit Interview", {"employee": request.employee, "docstatus": ["!=", 2]})
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Exit Interview",
			"employee": request.employee,
			"company": request.company,
			"status": "Pending",
			"ref_doctype": request.doctype,
			"reference_document_name": request.name,
			"custom_separation_request": request.name,
			"custom_separation_type": request.separation_type,
			"custom_personal_email": request.personal_email,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


# ---- Exit Interview hooks (doc_events) -------------------------------------------------


def validate_exit_interview(doc, method=None):
	"""Part I band, the data HR needs to schedule, and the completion rule for interviews from this process."""
	doc.custom_service_band = service_band(doc.date_of_joining, doc.relieving_date)
	if not doc.get("custom_separation_request"):
		return  # an interview HR opened by hand keeps the standard behaviour

	if doc.status == "Scheduled" and not (doc.date and doc.interviewers):
		frappe.throw(_("Enter the interview Date and the Interviewers before scheduling."))

	if doc.status == "Completed":
		answered = doc.get("custom_response") and frappe.db.get_value(
			"Exit Interview Response", doc.custom_response, "docstatus"
		) == 1
		if not answered and not (doc.get("custom_waive_reason") or "").strip():
			frappe.throw(
				_(
					"The employee has not submitted the exit questionnaire. Wait for it, or enter a reason in "
					"Response Waived Reason to complete without it."
				)
			)


def on_exit_interview_update(doc, method=None):
	"""Scheduling the interview gives the employee their questionnaire."""
	if doc.status != "Scheduled" or doc.get("custom_response") or not doc.get("custom_separation_request"):
		return
	create_response(doc)


def create_response(interview):
	user = frappe.db.get_value("Employee", interview.employee, "user_id")
	template_name = get_template()
	if not template_name:
		frappe.msgprint(_("No active Exit Interview Template found. The employee was not sent a questionnaire."), indicator="orange")
		return None
	if not user:
		frappe.msgprint(
			_("Employee {0} has no user account, so the questionnaire cannot be assigned to them.").format(interview.employee),
			indicator="orange",
		)
		return None

	template = frappe.get_doc("Exit Interview Template", template_name)
	prefilled = prefilled_answers(interview)
	response = frappe.new_doc("Exit Interview Response")
	response.employee = interview.employee
	response.exit_interview = interview.name
	response.template = template.name
	for q in template.questions:
		response.append(
			"answers",
			{
				"part": q.part,
				"question": q.question,
				"answer_type": q.answer_type,
				"options": q.options,
				"mandatory": q.mandatory,
				"answer": prefilled.get(q.question),
			},
		)
	response.insert(ignore_permissions=True)
	# the employee owns the response: they can open and fill it, and nobody else outside HR can see it
	frappe.db.set_value("Exit Interview Response", response.name, "owner", user, update_modified=False)
	interview.db_set("custom_response", response.name)

	notify_employee(interview, response, user)
	return response.name


def get_template():
	return frappe.db.get_value("Exit Interview Template", TEMPLATE_NAME, "name") or frappe.db.get_value(
		"Exit Interview Template", {"is_active": 1}, "name", order_by="creation"
	)


def prefilled_answers(interview):
	answers = {SERVICE_QUESTION: service_band(interview.date_of_joining, interview.relieving_date)}
	answer = TYPE_ANSWERS.get(interview.get("custom_separation_type"))
	if answer:
		answers[TYPE_QUESTION] = answer
	return answers


def notify_employee(interview, response, user):
	link = get_url_to_form("Exit Interview Response", response.name)
	subject = _("Exit interview: please complete your questionnaire")
	try:
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"subject": subject,
				"document_type": "Exit Interview Response",
				"document_name": response.name,
				"from_user": frappe.session.user,
			}
		).insert(ignore_permissions=True)
		recipients = [e for e in (interview.email, interview.get("custom_personal_email")) if e]
		if recipients:
			frappe.sendmail(
				recipients=recipients,
				subject=subject,
				message=_(
					"Dear {0},<br><br>Your exit interview is scheduled for {1}. Please complete the confidential "
					'exit questionnaire before then: <a href="{2}">open the questionnaire</a>. Only HR can read '
					"your answers.<br><br>Human Resources"
				).format(interview.employee_name, frappe.format(interview.date, {"fieldtype": "Date"}), link),
				reference_doctype=response.doctype,
				reference_name=response.name,
			)
	except Exception:  # a mail problem (e.g. no outgoing account) must not undo the scheduling
		frappe.log_error(title=f"Exit questionnaire notification failed: {response.name}")
