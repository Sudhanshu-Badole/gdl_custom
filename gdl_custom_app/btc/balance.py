"""Wallet balances (from the Stock Ledger's Zone/Custodian dimensions) and restriction-aware availability."""

import frappe
from frappe import _
from frappe.utils import flt, getdate


def get_wallet_balance(item_code, warehouse, zone, wallet, as_of_date=None):
	extra, params = "", [item_code, warehouse, zone, wallet]
	if as_of_date:
		extra = " and posting_date <= %s"
		params.append(getdate(as_of_date))
	return flt(
		frappe.db.sql(
			f"""select coalesce(sum(actual_qty), 0) from `tabStock Ledger Entry`
			where item_code=%s and warehouse=%s and zone=%s and custodian=%s and is_cancelled=0{extra}""",
			params,
		)[0][0],
		9,
	)


def get_restricted_qty(item_code, warehouse, zone, wallet, on_date, exclude=None):
	"""Quantity under an active Trading/Loan/Pledged restriction on on_date (expiry day included)."""
	on_date = getdate(on_date)
	extra, params = "", [item_code, warehouse, zone, wallet, on_date, on_date]
	if exclude:
		extra = " and name != %s"
		params.append(exclude)
	return flt(
		frappe.db.sql(
			f"""select coalesce(sum(qty - released_qty), 0) from `tabBTC Restriction`
			where item_code=%s and warehouse=%s and zone=%s and wallet=%s and state='Active'
			and start_date <= %s and expiry_date >= %s{extra}""",
			params,
		)[0][0],
		9,
	)


def get_available_qty(item_code, warehouse, zone, wallet, on_date, exclude=None):
	return flt(
		get_wallet_balance(item_code, warehouse, zone, wallet, on_date)
		- get_restricted_qty(item_code, warehouse, zone, wallet, on_date, exclude),
		9,
	)


def lock_item_warehouse(item_code, warehouse):
	"""Serialise concurrent submissions that spend the same BTC (row lock on the Bin)."""
	frappe.db.sql(
		"select name from `tabBin` where item_code=%s and warehouse=%s for update", (item_code, warehouse)
	)


def validate_available(item_code, warehouse, requests, on_date, label=None):
	"""requests: {(zone, wallet): qty}. Throws if any wallet lacks unrestricted BTC."""
	lock_item_warehouse(item_code, warehouse)
	for (zone, wallet), qty in requests.items():
		balance = get_wallet_balance(item_code, warehouse, zone, wallet, on_date)
		restricted = get_restricted_qty(item_code, warehouse, zone, wallet, on_date)
		available = flt(balance - restricted, 9)
		if flt(qty, 9) > available:
			frappe.throw(
				_(
					"{0}Wallet {1} in Zone {2} has {3} BTC available ({4} balance, {5} restricted); {6} BTC requested."
				).format(f"{label}: " if label else "", wallet, zone, available, balance, restricted, flt(qty, 9)),
				title=_("Insufficient Available BTC"),
			)
