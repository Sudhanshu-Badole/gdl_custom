"""Full and Final Statement extension for the separation process.

* creation is blocked until the Exit Interview is Completed;
* benefits and recoveries are calculated from the Separation Benefit Type formulas and tagged with the
  A-F section of the GDL statement layout;
* submission is blocked while a clearance item is open or the nomination is not valid (without a reason);
* net payable and the payee split (nominees on demise) are kept on the statement.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, get_link_to_form, getdate, nowdate

from gdl_custom_app.gdl_hr.doctype.separation_request.separation_request import HR_ROLES, has_any_role

SECTION_EARNED = "A. Earned Pay"
SECTION_BENEFITS = "B. Separation Benefits"
SECTION_RECOVERIES = "C. Recoveries"
SECTION_STATUTORY = "D. Statutory Deductions"
SECTION_OUTSIDE = "F. Paid Outside GDL"

PAYABLE_SECTIONS = (SECTION_EARNED, SECTION_BENEFITS)
INFORMATION_SECTIONS = (SECTION_STATUTORY, SECTION_OUTSIDE)

# HRMS pulls these rows into the statement; they get their section from the document type.
DEFAULT_SECTION = {
	"Salary Slip": SECTION_EARNED,
	"Additional Salary": SECTION_EARNED,
	"Expense Claim": SECTION_EARNED,
	"Leave Encashment": SECTION_EARNED,
	"Gratuity": SECTION_BENEFITS,
}

EVAL_GLOBALS = {"min": min, "max": max, "round": round, "int": int, "float": float, "abs": abs}
ACTIVE_STATES = ("Approved by CEO", "HR Acknowledged")


# ---- the separation request behind a statement ---------------------------------------------------


def get_process_request(employee):
	"""The approved Separation Request for this employee, or None when the exit is not run through the process."""
	rows = frappe.get_all(
		"Separation Request",
		filters={"employee": employee, "workflow_state": ["in", ACTIVE_STATES]},
		fields=[
			"name",
			"separation_type",
			"exit_interview",
			"employee_separation",
			"nomination_reason",
			"notice_days",
			"notice_served_days",
			"notice_shortfall_days",
		],
		order_by="creation desc",
		limit=1,
	)
	return rows[0] if rows else None


def is_demise(separation_type):
	return bool(frappe.db.get_value("Separation Type", separation_type, "skip_employee_clearance"))


# ---- document hooks -----------------------------------------------------------------------------


def before_insert(doc, method=None):
	"""Runs after HRMS has pulled the payables, receivables and assets."""
	request = get_process_request(doc.employee)
	if not request:
		return
	check_exit_interview(request)
	link_request(doc, request)
	drop_empty_placeholders(doc)
	apply_benefit_types(doc, request)
	add_statutory_items(doc)


def before_validate(doc, method=None):
	for row in doc.get("payables", []):
		if not row.get("custom_section"):
			row.custom_section = DEFAULT_SECTION.get(row.reference_document_type) or SECTION_EARNED
	for row in doc.get("receivables", []):
		if not row.get("custom_section"):
			row.custom_section = SECTION_RECOVERIES


def validate(doc, method=None):
	"""Runs after HRMS set_totals."""
	if doc.employee:
		from gdl_custom_app.gdl_hr.nomination import get_nomination_status

		doc.custom_nomination_status = get_nomination_status(doc.employee)
	set_net_payable(doc)
	set_payees(doc)


def before_submit(doc, method=None):
	request = get_process_request(doc.employee)
	if not request:
		return
	check_exit_interview(request)
	check_clearance(request)
	check_nomination(doc)
	check_accounts(doc)


# ---- creation checks ----------------------------------------------------------------------------


def check_exit_interview(request):
	"""Benefit calculation starts only after the exit interview is Completed (not for a demise)."""
	if is_demise(request.separation_type):
		return
	status = request.exit_interview and frappe.db.get_value("Exit Interview", request.exit_interview, "status")
	if status != "Completed":
		frappe.throw(
			_("The Exit Interview must be Completed before the Full and Final Statement is prepared. Current status: {0}.").format(
				status or _("not created")
			),
			title=_("Exit Interview Pending"),
		)


def drop_empty_placeholders(doc):
	"""HRMS adds an empty row per possible payable and receivable (Gratuity, Bonus, Employee Advance, ...).
	Each needs a reference document, so drop the ones that point at nothing; HR adds a row for a real document."""
	for table in ("payables", "receivables"):
		doc.set(table, [r for r in doc.get(table) if r.reference_document or flt(r.amount)])


def link_request(doc, request):
	doc.custom_separation_request = request.name
	doc.custom_separation_type = request.separation_type
	doc.custom_employee_separation = request.employee_separation
	doc.custom_exit_interview = request.exit_interview
	doc.custom_notice_shortfall_days = request.notice_shortfall_days
	doc.custom_nomination_reason = request.nomination_reason


# ---- submit checks ------------------------------------------------------------------------------


def open_clearance_items(employee_separation):
	"""Names of clearance activities whose task is not completed. A separation that is not submitted has none done."""
	if not employee_separation:
		return [_("the Employee Separation record has not been created")]
	es = frappe.db.get_value("Employee Separation", employee_separation, "docstatus")
	if es != 1:
		return [_("Employee Separation {0} is not submitted").format(employee_separation)]
	activities = frappe.get_all(
		"Employee Boarding Activity",
		filters={"parent": employee_separation, "parenttype": "Employee Separation"},
		fields=["activity_name", "task"],
	)
	open_items = []
	for row in activities:
		status = row.task and frappe.db.get_value("Task", row.task, "status")
		if status != "Completed":
			open_items.append(row.activity_name)
	return open_items


def check_clearance(request):
	"""Rule: the statement cannot be submitted for payment while any clearance item is open."""
	open_items = open_clearance_items(request.employee_separation)
	if open_items:
		frappe.throw(
			_("The statement cannot be submitted while clearance is open:<br>{0}").format("<br>".join(open_items)),
			title=_("Clearance Open"),
		)


def check_nomination(doc):
	from gdl_custom_app.gdl_hr.nomination import VALID, get_nomination_status

	"""On a demise the nominees are paid, so a nomination that is not valid needs a recorded reason."""
	if not is_demise(doc.custom_separation_type):
		return
	status = get_nomination_status(doc.employee)
	if status != VALID and not (doc.custom_nomination_reason or "").strip():
		frappe.throw(
			_(
				"The employee's nomination is not valid ({0}), so benefits cannot be split between nominees. "
				"Enter the Reason to Proceed Without a Valid Nomination first."
			).format(status)
		)


def check_accounts(doc):
	"""Rows calculated by this module need an account to post to."""
	missing = [
		str(row.idx)
		for table in ("payables", "receivables")
		for row in doc.get(table, [])
		if row.get("custom_benefit_type") and flt(row.amount) > 0 and not row.account and not row.paid_via_salary_slip
	]
	if missing:
		frappe.throw(_("Enter the Account on row(s): {0}").format(", ".join(missing)))


# ---- benefits and recoveries ----------------------------------------------------------------------


def applicable_benefit_types(separation_type):
	names = frappe.get_all("Separation Benefit Type", filters={"is_active": 1}, pluck="name", order_by="section, creation")
	result = []
	for name in names:
		allowed = frappe.get_all(
			"Separation Benefit Applicability", filters={"parent": name, "parenttype": "Separation Benefit Type"}, pluck="separation_type"
		)
		if not allowed or separation_type in allowed:
			result.append(frappe.get_cached_doc("Separation Benefit Type", name))
	return result


def get_formula_context(doc, request):
	"""The values a benefit formula can use."""
	emp = frappe.db.get_value(
		"Employee",
		doc.employee,
		["date_of_joining", "relieving_date", "custom_bond_amount", "custom_bond_start_date", "custom_bond_end_date"],
		as_dict=True,
	)
	end = getdate(emp.relieving_date or doc.relieving_date or nowdate())
	months = date_diff(end, getdate(emp.date_of_joining)) / 30.4375 if emp.date_of_joining else 0
	ctx = {
		"service_months": round(months, 2),
		"service_years": round(months / 12, 2),
		"completed_years": int(months // 12),
		"notice_days": flt(request.notice_days) if request else 0,
		"notice_served_days": flt(request.notice_served_days) if request else 0,
		"notice_shortfall_days": flt(request.notice_shortfall_days) if request else 0,
		"bond_amount": flt(emp.custom_bond_amount),
		"bond_unserved_ratio": bond_unserved_ratio(emp, end),
		"gross_pay": 0,
		"net_pay": 0,
	}
	slip = last_salary_slip(doc.employee)
	if slip:
		ctx["gross_pay"] = flt(slip.gross_pay)
		ctx["net_pay"] = flt(slip.net_pay)
		for row in [*slip.earnings, *slip.deductions]:
			if row.abbr:
				ctx[row.abbr] = ctx.get(row.abbr, 0) + flt(row.amount)
	return ctx


def bond_unserved_ratio(emp, end):
	"""Share of the training bond period still to run at the relieving date (0 when there is no bond)."""
	if not (flt(emp.custom_bond_amount) and emp.custom_bond_start_date and emp.custom_bond_end_date):
		return 0
	total = date_diff(emp.custom_bond_end_date, emp.custom_bond_start_date)
	left = date_diff(emp.custom_bond_end_date, end)
	if total <= 0:
		return 0
	return max(0, min(1, left / total))


def last_salary_slip(employee):
	name = frappe.db.get_value(
		"Salary Slip", {"employee": employee, "docstatus": 1}, "name", order_by="end_date desc"
	)
	return frappe.get_doc("Salary Slip", name) if name else None


def evaluate_formula(benefit, ctx):
	try:
		return flt(frappe.safe_eval(benefit.formula, dict(EVAL_GLOBALS), dict(ctx)))
	except NameError as e:
		frappe.throw(
			_("Formula of {0} uses {1}, which is not available for this employee (for example, no salary slip has that component).").format(
				frappe.bold(benefit.name), frappe.bold(str(e))
			),
			title=_("Benefit Formula Error"),
		)
	except Exception as e:
		frappe.throw(_("Formula of {0} could not be calculated: {1}").format(frappe.bold(benefit.name), str(e)), title=_("Benefit Formula Error"))


def benefit_account(benefit, company):
	if benefit.account:
		return benefit.account
	if benefit.salary_component:
		return frappe.db.get_value(
			"Salary Component Account", {"parent": benefit.salary_component, "company": company}, "account"
		)


def apply_benefit_types(doc, request=None):
	"""Add a row for every applicable benefit and recovery. Existing calculated rows are left alone."""
	request = request or get_process_request(doc.employee)
	separation_type = request.separation_type if request else doc.get("custom_separation_type")
	existing = {r.custom_benefit_type for r in [*doc.get("payables", []), *doc.get("receivables", [])] if r.get("custom_benefit_type")}
	ctx = get_formula_context(doc, request)

	for benefit in applicable_benefit_types(separation_type):
		if benefit.name in existing or benefit.section in INFORMATION_SECTIONS:
			continue
		amount = evaluate_formula(benefit, ctx)
		if amount <= 0 and not benefit.mandatory:
			continue
		row = {
			"status": "Unsettled",
			"component": benefit.name,
			"custom_section": benefit.section,
			"custom_benefit_type": benefit.name,
			"custom_clause_reference": benefit.description,
			"amount": amount,
			"account": benefit_account(benefit, doc.company),
			"remark": benefit.description,
		}
		doc.append("payables" if benefit.section in PAYABLE_SECTIONS else "receivables", row)


def add_statutory_items(doc):
	"""Section D: the statutory deductions taken in the last salary slip, shown for information."""
	if any(r.section == SECTION_STATUTORY for r in doc.get("custom_information_items", [])):
		return
	slip = last_salary_slip(doc.employee)
	if not slip:
		return
	for row in slip.deductions:
		if row.statistical_component or not flt(row.amount):
			continue
		doc.append(
			"custom_information_items",
			{"section": SECTION_STATUTORY, "description": _("{0} (final salary slip)").format(row.salary_component), "amount": row.amount},
		)


@frappe.whitelist()
def recalculate_benefits(statement):
	"""Replace the calculated rows that are still unsettled with fresh figures."""
	doc = frappe.get_doc("Full and Final Statement", statement)
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw(_("Only a draft statement can be recalculated."))
	for table in ("payables", "receivables"):
		doc.set(
			table,
			[r for r in doc.get(table) if not (r.get("custom_benefit_type") and r.status == "Unsettled")],
		)
	apply_benefit_types(doc)
	doc.save()
	return doc.name


# ---- totals and payees ----------------------------------------------------------------------------


def set_net_payable(doc):
	def total(table, section):
		return sum(flt(r.amount) for r in doc.get(table, []) if r.get("custom_section") == section)

	doc.custom_total_earned = total("payables", SECTION_EARNED)
	doc.custom_total_benefits = total("payables", SECTION_BENEFITS)
	doc.custom_total_recoveries = flt(doc.total_receivable_amount)
	doc.custom_net_payable = flt(doc.total_payable_amount) - flt(doc.total_receivable_amount)


def set_payees(doc):
	"""The employee is paid, except on a demise where the nominees share the net amount by their percentage."""
	doc.set("custom_payees", [])
	net = max(0, flt(doc.custom_net_payable))
	nominees = []
	if doc.get("custom_separation_type") and is_demise(doc.custom_separation_type):
		nominees = frappe.get_all(
			"Employee Nominee",
			filters={"parent": f"NOM-{doc.employee}", "parenttype": "Employee Nomination"},
			fields=["nominee_name", "relationship", "share_percent"],
			order_by="idx",
		)
	if nominees:
		for n in nominees:
			doc.append(
				"custom_payees",
				{
					"nominee_name": n.nominee_name,
					"relationship": n.relationship,
					"share_percent": n.share_percent,
					"amount": flt(net * flt(n.share_percent) / 100, 2),
				},
			)
	elif doc.employee:
		doc.append(
			"custom_payees",
			{"nominee_name": doc.employee_name, "relationship": _("Employee"), "share_percent": 100, "amount": net},
		)


@frappe.whitelist()
def create_journal_entry(statement):
	"""Finance builds the payment journal entry from a submitted statement. The HRMS button posts the whole
	document back, which Frappe treats as a submit, so Finance (read only) uses this instead."""
	doc = frappe.get_doc("Full and Final Statement", statement)
	doc.check_permission("read")
	if not has_any_role((*HR_ROLES, "Accounts Manager", "Accounts User")):
		frappe.throw(_("Only HR and Finance can create the journal entry."), frappe.PermissionError)
	if doc.docstatus != 1 or doc.status != "Unpaid":
		frappe.throw(_("A journal entry can only be created from a submitted, unpaid statement."))
	return doc.create_journal_entry().as_dict()


# ---- starting a statement from the request ---------------------------------------------------------


@frappe.whitelist()
def start_full_and_final(request):
	"""HR starts the statement for an acknowledged request."""
	if not has_any_role(HR_ROLES):
		frappe.throw(_("Only HR can prepare the Full and Final Statement."), frappe.PermissionError)
	req = frappe.get_doc("Separation Request", request)
	if req.workflow_state != "HR Acknowledged":
		frappe.throw(_("The request must be HR Acknowledged first."))
	existing = frappe.db.exists("Full and Final Statement", {"employee": req.employee, "docstatus": ["!=", 2]})
	if existing:
		req.db_set("full_and_final_statement", existing)
		return existing

	emp = frappe.db.get_value("Employee", req.employee, ["company", "relieving_date", "date_of_joining"], as_dict=True)
	doc = frappe.get_doc(
		{
			"doctype": "Full and Final Statement",
			"employee": req.employee,
			"company": emp.company,
			"transaction_date": nowdate(),
			"relieving_date": emp.relieving_date,
			"date_of_joining": emp.date_of_joining,
		}
	)
	doc.insert()
	req.db_set("full_and_final_statement", doc.name)
	return doc.name
