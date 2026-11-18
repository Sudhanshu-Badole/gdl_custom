"""Wallet balances (from the Stock Ledger's Zone/Wallet dimensions) and restriction-aware availability."""

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
			where item_code=%s and warehouse=%s and zone=%s and wallet=%s and is_cancelled=0{extra}""",
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


def get_available_by_zone_wallet(item_code, warehouse, on_date=None, wallet=None, zone=None, exclude_restriction=None):
	"""[{zone, wallet, balance, restricted, available}] for each zone/wallet holding BTC (zero rows hidden)."""
	conditions, params = "", [item_code, warehouse]
	if on_date:
		conditions += " and posting_date <= %s"
		params.append(getdate(on_date))
	for field, value in (("wallet", wallet), ("zone", zone)):
		if value:
			conditions += f" and {field} = %s"
			params.append(value)
	rows = frappe.db.sql(
		f"""select zone, wallet, sum(actual_qty) as balance from `tabStock Ledger Entry`
		where item_code=%s and warehouse=%s and is_cancelled=0 and ifnull(zone,'')!='' and ifnull(wallet,'')!=''{conditions}
		group by zone, wallet order by wallet, zone""",
		params,
		as_dict=True,
	)
	# one grouped query for the active restrictions of every wallet/zone (not one query per row)
	on = getdate(on_date or frappe.utils.today())
	restr_extra, restr_params = "", [item_code, warehouse, on, on]
	if exclude_restriction:
		restr_extra = " and name != %s"
		restr_params.append(exclude_restriction)
	restricted = {
		(r.zone, r.wallet): flt(r.qty, 9)
		for r in frappe.db.sql(
			f"""select zone, wallet, coalesce(sum(qty - released_qty), 0) as qty from `tabBTC Restriction`
			where item_code=%s and warehouse=%s and state='Active' and start_date <= %s and expiry_date >= %s{restr_extra}
			group by zone, wallet""",
			restr_params,
			as_dict=True,
		)
	}

	result = []
	for row in rows:
		balance = flt(row.balance, 9)
		held = restricted.get((row.zone, row.wallet), 0)
		available = flt(balance - held, 9)
		if balance or available:
			result.append({"zone": row.zone, "wallet": row.wallet, "balance": balance, "restricted": held, "available": available})
	return result


@frappe.whitelist()
def get_zone_wallet_balances(item_code=None, warehouse=None, wallet=None, zone=None, on_date=None):
	"""Form popup: available BTC per zone and wallet (defaults to the BTC item and warehouse)."""
	settings = frappe.get_cached_doc("GDL Setting")
	item_code = item_code or settings.btc_item
	warehouse = warehouse or settings.btc_warehouse
	if not item_code or not warehouse:
		return []
	return get_available_by_zone_wallet(item_code, warehouse, on_date, wallet, zone)


@frappe.whitelist()
def allocate_wallet_qty(wallet, qty, item_code=None, warehouse=None, on_date=None):
	"""Quick Enter: split qty of one wallet across its zones, largest available balance first.

	Returns [{zone, wallet, qty}]; throws when the wallet cannot cover qty.
	"""
	qty = flt(qty, 9)
	if qty <= 0:
		frappe.throw(_("Enter a quantity greater than zero."))
	available = [r for r in get_zone_wallet_balances(item_code, warehouse, wallet=wallet, on_date=on_date) if r["available"] > 0]
	total = flt(sum(r["available"] for r in available), 9)
	if qty > total:
		frappe.throw(
			_("Wallet {0} has {1} BTC available across its zones; {2} BTC requested.").format(wallet, total, qty),
			title=_("Insufficient Available BTC"),
		)
	remaining, rows = qty, []
	for r in sorted(available, key=lambda r: -r["available"]):
		take = flt(min(remaining, r["available"]), 9)
		rows.append({"zone": r["zone"], "wallet": wallet, "qty": take})
		remaining = flt(remaining - take, 9)
		if not remaining:
			break
	return rows


@frappe.whitelist()
def get_row_balance(item_code, warehouse, zone, wallet, on_date=None):
	"""Available BTC (net of restrictions) for one zone + wallet; for the row Balance field."""
	if not (item_code and warehouse and zone and wallet):
		return 0
	return get_available_qty(item_code, warehouse, zone, wallet, on_date or frappe.utils.today())


def set_row_balances(doc, method=None):
	"""validate: fill each source row's Balance = available for its zone + wallet minus the qty on the rows above
	that draw from the same zone + wallet (so the second row shows what is left after the first)."""
	if doc.docstatus != 0:
		return
	settings = frappe.get_cached_doc("GDL Setting")
	if not settings.enable_btc_rules or not settings.btc_item:
		return
	is_stock_entry = doc.doctype == "Stock Entry"
	used = {}
	for row in doc.get("items") or []:
		warehouse = row.get("s_warehouse") if is_stock_entry else row.get("warehouse")
		if row.item_code != settings.btc_item or not warehouse or not row.get("zone") or not row.get("wallet"):
			row.custom_balance = 0
			continue
		key = (row.zone, row.wallet)
		available = get_available_qty(row.item_code, warehouse, row.zone, row.wallet, doc.posting_date or frappe.utils.today())
		row.custom_balance = flt(available - used.get(key, 0), 9)
		used[key] = flt(used.get(key, 0) + flt(row.get("transfer_qty") or row.qty), 9)
