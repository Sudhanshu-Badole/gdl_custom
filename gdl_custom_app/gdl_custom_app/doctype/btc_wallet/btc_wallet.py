import frappe
from frappe import _
from frappe.model.document import Document


class BTCWallet(Document):
	def validate(self):
		if not frappe.db.get_value("BTC Custodian", self.custodian, "is_active") and self.is_new():
			frappe.throw(_("Custodian {0} is inactive.").format(self.custodian))
		if self.has_value_changed("is_active") and not self.is_active and not self.is_new():
			self.validate_no_balance()

	def validate_no_balance(self):
		bal = frappe.db.sql(
			"select coalesce(sum(actual_qty),0) from `tabStock Ledger Entry` where custodian=%s and is_cancelled=0",
			self.name,
		)[0][0]
		if bal:
			frappe.throw(_("Cannot deactivate wallet {0}: it still holds {1} BTC.").format(self.name, bal))
