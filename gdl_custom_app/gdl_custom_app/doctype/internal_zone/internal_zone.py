import frappe
from frappe import _
from frappe.model.document import Document

# Stock-ledger columns an Internal Zone can be referenced from.
ZONE_REFERENCES = (
	("Stock Ledger Entry", "zone"),
	("Stock Entry Detail", "zone"),
	("Stock Entry Detail", "to_zone"),
)


class InternalZone(Document):
	def validate(self):
		self.validate_cost_center()
		if self.has_value_changed("is_active") and not self.is_active and not self.is_new():
			self.validate_not_used("deactivate")

	def on_trash(self):
		self.validate_not_used("delete")

	def validate_cost_center(self):
		if not self.default_cost_center:
			return  # reported by the mandatory-field check
		cc = frappe.db.get_value(
			"Cost Center", self.default_cost_center, ["company", "is_group", "disabled"], as_dict=True
		)
		if not cc:
			frappe.throw(_("Default Cost Center {0} does not exist.").format(self.default_cost_center))
		if cc.company != self.company:
			frappe.throw(_("Cost Center {0} belongs to {1}, not {2}.").format(self.default_cost_center, cc.company, self.company))
		if cc.is_group or cc.disabled:
			frappe.throw(_("Cost Center {0} must be an enabled, non-group Cost Center.").format(self.default_cost_center))

	def validate_not_used(self, action):
		for doctype, field in ZONE_REFERENCES:
			if frappe.db.exists(doctype, {field: self.name}):
				frappe.throw(
					_("Cannot {0} Zone {1}: it is used in submitted transactions ({2}).").format(action, self.name, doctype)
				)
