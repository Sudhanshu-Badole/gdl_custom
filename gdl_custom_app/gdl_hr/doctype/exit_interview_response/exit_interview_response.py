import frappe
from frappe import _
from frappe.model.document import Document

from gdl_custom_app.gdl_hr.doctype.separation_request.separation_request import HR_ROLES, has_any_role

CHOICE_TYPES = ("Single Choice", "Rating 4", "Rating 5")
LOCKED_COLUMNS = ("part", "question", "answer_type", "options", "mandatory")


class ExitInterviewResponse(Document):
	def validate(self):
		self.validate_requester()
		self.validate_questions_unchanged()
		self.validate_answers()

	def before_submit(self):
		for row in self.answers:
			if row.mandatory and not (row.answer or "").strip():
				frappe.throw(_("Please answer: \"{0}\"").format(row.question))

	# ---- validation -----------------------------------------------------------------

	def validate_requester(self):
		if not self.is_new() or has_any_role(HR_ROLES):
			return
		user = frappe.db.get_value("Employee", self.employee, "user_id")
		if user != frappe.session.user:
			frappe.throw(_("You can only fill in your own exit questionnaire."))

	def validate_questions_unchanged(self):
		"""The employee answers; the questions and options come from the template and cannot be edited."""
		before = self.get_doc_before_save()
		if not before or has_any_role(("System Manager",)):
			return
		if len(before.answers) != len(self.answers):
			frappe.throw(_("Questions cannot be added or removed."))
		for old, new in zip(before.answers, self.answers):
			for fieldname in LOCKED_COLUMNS:
				if old.get(fieldname) != new.get(fieldname):
					frappe.throw(_("Row #{0}: only the Answer can be changed.").format(new.idx))

	def validate_answers(self):
		for row in self.answers:
			answer = (row.answer or "").strip()
			if not answer:
				continue
			options = [o.strip() for o in (row.options or "").splitlines() if o.strip()]
			if row.answer_type in CHOICE_TYPES and options and answer not in options:
				frappe.throw(_("Row #{0}: choose one of the listed options.").format(row.idx))
			if row.answer_type == "Multi Select" and options:
				chosen = [a.strip() for a in answer.splitlines() if a.strip()]
				if any(c not in options for c in chosen):
					frappe.throw(_("Row #{0}: choose only from the listed options, one per line.").format(row.idx))


# ---- permissions --------------------------------------------------------------------


def get_permission_query_conditions(user=None):
	user = user or frappe.session.user
	if set(HR_ROLES) & set(frappe.get_roles(user)):
		return ""
	return "`tabExit Interview Response`.owner = {0}".format(frappe.db.escape(user))


def has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if set(HR_ROLES) & set(frappe.get_roles(user)):
		return True
	if doc.is_new() or not doc.name:
		return True
	return user == doc.owner
