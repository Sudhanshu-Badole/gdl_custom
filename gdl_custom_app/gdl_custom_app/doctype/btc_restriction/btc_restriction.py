import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_datetime, getdate, now_datetime, nowdate

from gdl_custom_app.btc.balance import get_available_qty

# Changing these directly would bypass the audited release / extend paths.
PROTECTED = ("qty", "released_qty", "state", "expiry_date", "start_date", "wallet", "zone", "restriction_type")


class BTCRestriction(Document):
	def validate(self):
		if flt(self.qty) <= 0:
			frappe.throw(_("Restricted Qty must be greater than zero."))
		if getdate(self.expiry_date) < getdate(self.start_date):
			frappe.throw(_("Expiry Date cannot be before Start Date."))
		self.remaining_qty = flt(flt(self.qty) - flt(self.released_qty), 9)

		if self.is_new():
			self.original_expiry_date = self.expiry_date
			self.validate_masters()
			self.validate_not_over_allocated()
		elif not self.flags.via_service:
			changed = [f for f in PROTECTED if self.has_value_changed(f)]
			if changed:
				frappe.throw(
					_("{0} can only be changed through Release or Extend.").format(", ".join(changed))
				)

	def validate_masters(self):
		if not frappe.db.get_value("Internal Zone", self.zone, "is_active"):
			frappe.throw(_("Zone {0} is inactive.").format(self.zone))
		active, company = frappe.db.get_value("BTC Wallet", self.wallet, ["is_active", "company"])
		if not active or company != self.company:
			frappe.throw(_("Wallet {0} is inactive or belongs to another company.").format(self.wallet))

	def validate_not_over_allocated(self):
		available = get_available_qty(self.item_code, self.warehouse, self.zone, self.wallet, self.start_date)
		if flt(self.qty, 9) > available:
			frappe.throw(
				_("Cannot restrict {0} BTC: only {1} BTC of wallet {2} (zone {3}) is unrestricted.").format(
					self.qty, available, self.wallet, self.zone
				),
				title=_("Over-allocation"),
			)

	def on_trash(self):
		frappe.throw(_("BTC Restrictions are an audit record and cannot be deleted. Cancel or release instead."))


def _load(name):
	doc = frappe.get_doc("BTC Restriction", name)
	doc.check_permission("write")  # who may release/extend is configured with role permissions in the UI
	doc.flags.via_service = True
	return doc


@frappe.whitelist()
def release_restriction(name, qty=None, reason=None):
	"""Early release of `qty` (default: all remaining). Records user, time, quantity and reason."""
	doc = _load(name)
	if doc.state != "Active":
		frappe.throw(_("Restriction {0} is {1}; nothing to release.").format(name, doc.state))
	if not reason:
		frappe.throw(_("A reason is required for an early release."))
	remaining = flt(doc.qty - doc.released_qty, 9)
	qty = flt(qty, 9) or remaining
	if qty <= 0 or qty > remaining:
		frappe.throw(_("Release quantity must be between 0 and the remaining {0} BTC.").format(remaining))

	doc.released_qty = flt(doc.released_qty + qty, 9)
	doc.append(
		"release_log",
		{"kind": "Early Release", "qty": qty, "released_on": now_datetime(), "released_by": frappe.session.user, "reason": reason},
	)
	if flt(doc.qty - doc.released_qty, 9) == 0:
		doc.state = "Released"
	doc.save()
	return doc.name


@frappe.whitelist()
def extend_restriction(name, new_expiry, reason=None):
	"""Move the expiry later; the previous expiry stays in the extension history."""
	doc = _load(name)
	if doc.state != "Active" or getdate(doc.expiry_date) < getdate(nowdate()):
		frappe.throw(_("Only an active, unexpired restriction can be extended."))
	if getdate(new_expiry) <= getdate(doc.expiry_date):
		frappe.throw(_("New expiry must be after the current expiry {0}.").format(doc.expiry_date))
	doc.append(
		"extension_log",
		{"previous_expiry": doc.expiry_date, "new_expiry": new_expiry, "extended_on": now_datetime(),
		 "extended_by": frappe.session.user, "reason": reason},
	)
	doc.expiry_date = new_expiry
	doc.save()
	return doc.name


def expire_restrictions(today=None):
	"""Daily job: restrictions whose expiry date has passed become Available. Idempotent."""
	today = getdate(today or nowdate())
	names = frappe.get_all("BTC Restriction", filters={"state": "Active", "expiry_date": ["<", today]}, pluck="name")
	for name in names:
		doc = frappe.get_doc("BTC Restriction", name)
		doc.flags.via_service = True
		remaining = flt(doc.qty - doc.released_qty, 9)
		if remaining > 0:
			doc.append(
				"release_log",
				{"kind": "Expiry", "qty": remaining, "released_on": now_datetime(), "released_by": "Administrator",
				 "reason": _("Expired on {0}").format(doc.expiry_date)},
			)
		doc.released_qty = doc.qty
		doc.state = "Expired"
		doc.save(ignore_permissions=True)
	if names:
		frappe.logger("gdl_btc").info(f"Expired {len(names)} BTC restriction(s): {names}")
	return names
