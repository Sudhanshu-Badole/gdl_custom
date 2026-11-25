import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, flt, getdate, nowdate

# Roles that see every request and may file one for another employee.
HR_ROLES = ("System Manager", "HR Manager", "HR User")
FULL_READ_ROLES = (*HR_ROLES, "CEO", "HRA")

REASON_STATES = ("Rejected by Supervisor", "Rejected by CEO", "Withheld by CEO")
LOCKED_STATES = ("Approved by CEO", "HR Acknowledged")

# Fields the employee enters. After the request leaves Draft only HR may change them.
EMPLOYEE_FIELDS = (
	"employee",
	"separation_type",
	"resignation_date",
	"last_working_date",
	"notice_days",
	"resignation_letter",
	"personal_email",
	"reason_for_leaving",
	"handover_status",
)
LOCKED_DATE_FIELDS = ("resignation_date", "last_working_date", "notice_days")

NOTICE_REGULAR = 30
NOTICE_CONTRACT = 60
NOTICE_PROBATION = 7


class SeparationRequest(Document):
	def validate(self):
		self.validate_requester()
		self.validate_dates()
		self.set_notice_days()
		self.set_notice_tracker()
		self.set_obligation_flags()
		self.set_nomination_status()
		self.validate_blocks()
		self.validate_locked_fields()
		self.validate_decision_reason()
		self.validate_nomination_reason()

	def onload(self):
		"""The nomination changes outside this document: show its current status when the form opens."""
		if self.employee and self.workflow_state != "HR Acknowledged":
			from gdl_custom_app.gdl_hr.nomination import get_nomination_status

			self.nomination_status = get_nomination_status(self.employee)

	def on_update(self):
		if self.has_value_changed("workflow_state") or self.flags.in_insert:
			self.handle_state_change()

	# ---- validation -----------------------------------------------------------------

	def validate_requester(self):
		"""An employee can only file a request for themselves; HR may file on their behalf."""
		if not self.is_new() or has_any_role(HR_ROLES):
			return
		user = frappe.db.get_value("Employee", self.employee, "user_id")
		if user != frappe.session.user:
			frappe.throw(_("You can only submit a separation request for your own Employee record."))

	def validate_dates(self):
		if self.resignation_date and self.last_working_date and getdate(self.last_working_date) < getdate(
			self.resignation_date
		):
			frappe.throw(_("Last Working Date cannot be before the Resignation Date."))

	def set_notice_days(self):
		"""Probationers serve 7 days (rule 5); otherwise default by employment type."""
		if is_probationer(self.employee):
			self.notice_days = NOTICE_PROBATION
		elif not self.notice_days:
			self.notice_days = default_notice_days(self.employee)

	def set_notice_tracker(self):
		"""Served = days between resignation and last working date; shortfall feeds deduction D1."""
		if not (self.resignation_date and self.last_working_date):
			return
		self.notice_served_days = date_diff(self.last_working_date, self.resignation_date)
		self.notice_shortfall_days = max(0, flt(self.notice_days) - self.notice_served_days)

	def set_obligation_flags(self):
		emp = frappe.db.get_value(
			"Employee",
			self.employee,
			["status", "custom_under_investigation", "custom_training_study_undertaking"],
			as_dict=True,
		)
		self.open_salary_advance, self.open_travel_advance = open_advances(self.employee)
		undertaking = emp.custom_training_study_undertaking
		self.has_training_study_undertaking = 1 if undertaking and undertaking != "None" else 0
		self.is_suspended_or_under_investigation = (
			1 if emp.status == "Suspended" or emp.custom_under_investigation else 0
		)

	def set_nomination_status(self):
		from gdl_custom_app.gdl_hr.nomination import get_nomination_status

		self.nomination_status = get_nomination_status(self.employee)

	def validate_nomination_reason(self):
		"""Rule 7 is a warning: HR may acknowledge without a valid nomination, but records why."""
		if self.workflow_state == "HR Acknowledged" and self.has_value_changed("workflow_state"):
			if self.nomination_status != "Valid" and not (self.nomination_reason or "").strip():
				frappe.throw(
					_(
						"The employee's nomination is not valid ({0}). Enter the Reason to Proceed Without a Valid "
						"Nomination before acknowledging."
					).format(self.nomination_status)
				)

	def validate_blocks(self):
		"""Rule 1: a suspended or investigated employee cannot resign (blocks submission)."""
		submitting = self.is_new() or (
			self.workflow_state == "Pending Supervisor Approval" and self.has_value_changed("workflow_state")
		)
		if not submitting:
			return
		if self.is_suspended_or_under_investigation:
			frappe.throw(
				_("{0} is suspended or under investigation and cannot submit a separation request.").format(
					self.employee_name or self.employee
				)
			)
		if self.workflow_state == "Pending Supervisor Approval" and not self.supervisor_user:
			frappe.throw(_("The employee has no Immediate Supervisor with a user account. Ask HR to set Reports To."))

	def validate_locked_fields(self):
		before = self.get_doc_before_save()
		if not before or has_any_role(("System Manager",)):
			return
		old_state = before.workflow_state or "Draft"
		if old_state in LOCKED_STATES:
			for fieldname in LOCKED_DATE_FIELDS:
				if self.get(fieldname) != before.get(fieldname):
					frappe.throw(_("{0} is locked after CEO approval.").format(self.meta.get_label(fieldname)))
		elif old_state != "Draft" and not has_any_role(HR_ROLES):
			for fieldname in EMPLOYEE_FIELDS:
				if self.get(fieldname) != before.get(fieldname):
					frappe.throw(
						_("{0} can only be edited while the request is in Draft.").format(
							self.meta.get_label(fieldname)
						)
					)

	def validate_decision_reason(self):
		"""Rejection or withholding needs a reason (rules 2, workflow step 2.a and 3.a)."""
		if self.workflow_state in REASON_STATES and self.has_value_changed("workflow_state"):
			if not (self.decision_reason or "").strip():
				frappe.throw(_("Enter the Approver Comment / Reason before rejecting or withholding."))

	# ---- state changes --------------------------------------------------------------

	def handle_state_change(self):
		if self.workflow_state == "Approved by CEO":
			self.sync_to_employee()
			self.open_exit_interview()
		elif self.workflow_state == "HR Acknowledged" and not self.employee_separation:
			from gdl_custom_app.gdl_hr.separation import create_employee_separation

			name = create_employee_separation(self)
			self.db_set("employee_separation", name)

	def open_exit_interview(self):
		"""CEO approval starts the exit interview (needs the relieving date written just above)."""
		if self.exit_interview:
			return
		from gdl_custom_app.gdl_hr.exit_interview import create_exit_interview

		try:
			name = create_exit_interview(self)
		except Exception:  # the approval stands; HR can open the interview by hand
			frappe.log_error(title=f"Exit interview not created: {self.name}")
			frappe.msgprint(_("The exit interview could not be created automatically. Ask HR to create it."), indicator="orange")
			return
		if name:
			self.db_set("exit_interview", name)

	def sync_to_employee(self):
		"""CEO approval fixes the resignation date and last working day on the Employee."""
		frappe.db.set_value(
			"Employee",
			self.employee,
			{
				"resignation_letter_date": self.resignation_date,
				"relieving_date": self.last_working_date,
				"notice_number_of_days": self.notice_days,
				"held_on": self.last_working_date,
			},
		)


# ---- helpers ------------------------------------------------------------------------


def has_any_role(roles):
	return bool(set(roles) & set(frappe.get_roles()))


def is_probationer(employee):
	row = frappe.db.get_value(
		"Employee",
		employee,
		["employment_type", "scheduled_confirmation_date", "final_confirmation_date"],
		as_dict=True,
	)
	if not row:
		return False
	if row.employment_type and "probation" in row.employment_type.lower():
		return True
	return bool(
		row.scheduled_confirmation_date
		and not row.final_confirmation_date
		and getdate(row.scheduled_confirmation_date) > getdate(nowdate())
	)


def default_notice_days(employee):
	row = frappe.db.get_value("Employee", employee, ["employment_type", "notice_number_of_days"], as_dict=True)
	if row.employment_type and "contract" in row.employment_type.lower():
		return NOTICE_CONTRACT
	return row.notice_number_of_days or NOTICE_REGULAR


def open_advances(employee):
	"""(salary advance open, travel advance open) from unsettled Employee Advances.

	Employee Advance has no type field, so a purpose mentioning "travel" counts as a travel advance.
	"""
	advances = frappe.get_all(
		"Employee Advance",
		filters={"employee": employee, "docstatus": 1, "status": ["in", ["Paid", "Unpaid", "Partly Claimed and Returned"]]},
		fields=["purpose", "paid_amount", "claimed_amount", "return_amount"],
	)
	salary = travel = 0
	for adv in advances:
		if flt(adv.paid_amount) - flt(adv.claimed_amount) - flt(adv.return_amount) <= 0:
			continue
		if "travel" in (adv.purpose or "").lower():
			travel = 1
		else:
			salary = 1
	return salary, travel


# ---- permissions --------------------------------------------------------------------


def get_permission_query_conditions(user=None):
	user = user or frappe.session.user
	if set(FULL_READ_ROLES) & set(frappe.get_roles(user)):
		return ""
	quoted = frappe.db.escape(user)
	return (
		"(`tabSeparation Request`.owner = {u} or `tabSeparation Request`.supervisor_user = {u}"
		" or `tabSeparation Request`.employee_user = {u})"
	).format(u=quoted)


def has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if set(FULL_READ_ROLES) & set(frappe.get_roles(user)):
		return True
	if doc.is_new() or not doc.name:
		return True  # doctype-level and create checks: the list is scoped by the query conditions
	return user in (doc.owner, doc.get("supervisor_user"), doc.get("employee_user"))
