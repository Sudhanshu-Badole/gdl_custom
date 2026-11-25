import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from gdl_custom_app.gdl_hr.doctype.separation_request.separation_request import FULL_READ_ROLES, HR_ROLES, has_any_role

SHARE_PRECISION = 2
OPEN_STATES = ("Submitted", "Verified")


class EmployeeNomination(Document):
	def validate(self):
		self.validate_requester()
		self.validate_nominees()
		self.set_total()
		self.validate_state_rules()
		self.set_verification()

	# ---- validation -----------------------------------------------------------------

	def validate_requester(self):
		"""An employee files a nomination for themselves only; HR may file on their behalf."""
		if not self.is_new():
			return
		if frappe.db.exists("Employee Nomination", {"employee": self.employee}):
			frappe.throw(_("A nomination already exists for {0}. Edit that one instead.").format(self.employee))
		if has_any_role(HR_ROLES):
			return
		user = frappe.db.get_value("Employee", self.employee, "user_id")
		if user != frappe.session.user:
			frappe.throw(_("You can only file a nomination for your own Employee record."))

	def validate_nominees(self):
		for row in self.nominees:
			if flt(row.share_percent) <= 0 or flt(row.share_percent) > 100:
				frappe.throw(_("Row #{0}: the share of {1} must be more than 0 and at most 100%.").format(row.idx, row.nominee_name))

	def set_total(self):
		self.total_share = flt(sum(flt(r.share_percent) for r in self.nominees), SHARE_PRECISION)

	def validate_state_rules(self):
		before = self.get_doc_before_save()
		old_state = (before.workflow_state if before else None) or "Draft"
		new_state = self.workflow_state or "Draft"

		if new_state in OPEN_STATES and new_state != old_state:
			if not self.nominees:
				frappe.throw(_("Add at least one nominee before submitting."))
			if flt(self.total_share, SHARE_PRECISION) != 100:
				frappe.throw(_("The shares must total exactly 100%. They total {0}%.").format(self.total_share))

		if not before or has_any_role(("System Manager",)):
			return
		if old_state in OPEN_STATES and not has_any_role(HR_ROLES):
			frappe.throw(_("This nomination is with HR and can no longer be edited. Ask HR to return it to Draft."))
		if new_state == "Draft" and old_state in OPEN_STATES and not (self.remarks or "").strip():
			frappe.throw(_("Enter the reason in Remarks before returning the nomination to Draft."))

	def set_verification(self):
		if not self.has_value_changed("workflow_state"):
			return
		if self.workflow_state == "Verified":
			self.verified_by = frappe.session.user
			self.verified_on = nowdate()
		else:
			self.verified_by = None
			self.verified_on = None


# ---- permissions --------------------------------------------------------------------


def get_permission_query_conditions(user=None):
	user = user or frappe.session.user
	if set(FULL_READ_ROLES) & set(frappe.get_roles(user)):
		return ""
	quoted = frappe.db.escape(user)
	return "(`tabEmployee Nomination`.owner = {u} or `tabEmployee Nomination`.employee_user = {u})".format(u=quoted)


def has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if set(FULL_READ_ROLES) & set(frappe.get_roles(user)):
		return True
	if doc.is_new() or not doc.name:
		return True
	return user in (doc.owner, doc.get("employee_user"))
