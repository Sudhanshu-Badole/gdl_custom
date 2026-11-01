"""USD -> company-currency (BTN) rate from ERPNext's Currency Exchange master.

Uses the same filters as erpnext.setup.utils.get_exchange_rate (latest entry on
or before the date, optional for_buying / for_selling flag, stale-rate window)
but never calls the external rate API and never returns 0 or a "current" rate:
a missing rate is an error so the user fixes the master data.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate

USD = "USD"


def get_usd_rate(posting_date, side=None, company=None):
	"""Return the USD->company currency rate for posting_date.

	side: "for_buying" (receipts/purchases), "for_selling" (sales) or None.
	"""
	company_currency = frappe.get_cached_value(
		"Company", company or frappe.defaults.get_user_default("Company"), "default_currency"
	)
	if company_currency == USD:
		return 1.0

	posting_date = getdate(posting_date)
	filters = [
		["date", "<=", posting_date],
		["from_currency", "=", USD],
		["to_currency", "=", company_currency],
	]
	if side in ("for_buying", "for_selling"):
		filters.append([side, "=", 1])

	settings = frappe.get_cached_doc("Accounts Settings")
	if not settings.get("allow_stale"):
		filters.append(["date", ">", add_days(posting_date, -(settings.get("stale_days") or 0))])

	rows = frappe.get_all(
		"Currency Exchange",
		filters=filters,
		fields=["exchange_rate"],
		order_by="date desc, creation desc",
		limit=1,
	)
	if not rows or not flt(rows[0].exchange_rate):
		frappe.throw(
			_("No {0} to {1} exchange rate found on or before {2}{3}. Add it in Currency Exchange.").format(
				USD, company_currency, posting_date, f" ({side})" if side else ""
			),
			title=_("Missing Exchange Rate"),
		)
	return flt(rows[0].exchange_rate)
