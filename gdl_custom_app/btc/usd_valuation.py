"""Custom USD moving-average valuation of BTC, independent of ERPNext's BTN valuation.

One global pool per item (approved assumption - see GDL Setting): zone and wallet
are recorded on every row but do not split the average. All maths uses Decimal.

Rows are keyed by source_key (doctype|name|detail|direction) so a source row can
post once. Rows are never deleted: cancellation flags them (is_cancelled) and the
pool is rebuilt from the earliest affected point, which recomputes only the
derived columns (outgoing value, balances, average) of later live rows.
"""

from decimal import ROUND_HALF_UP, Decimal

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime

LEDGER = "BTC USD Valuation Ledger"
QTY_Q = Decimal("0.000000001")
VAL_Q = Decimal("0.0001")


def D(value):
	return Decimal(str(value or 0))


def _q(value, quantum):
	return value.quantize(quantum, rounding=ROUND_HALF_UP)


def posting_datetime(posting_date, posting_time):
	return get_datetime(f"{posting_date} {posting_time}")


def post_movement(
	*, company, item_code, qty, usd_rate, btn_rate, posting_date, posting_time, doctype, name,
	detail, transaction_type, warehouse=None, zone=None, cost_center=None, wallet=None, market_usd_rate=0,
):
	"""Post one movement (qty>0 in, qty<0 out; usd_rate ignored for out) and rebuild from it.

	Idempotent: returns the existing row if this source row already posted.
	"""
	qty = D(qty)
	if qty == 0:
		return None
	direction = "In" if qty > 0 else "Out"
	source_key = f"{doctype}|{name}|{detail}|{direction}"

	if existing := frappe.db.get_value(LEDGER, {"source_key": source_key}, "name"):
		return existing

	if direction == "In" and flt(usd_rate) < 0:
		frappe.throw(_("{0} {1}: USD rate cannot be negative.").format(doctype, name))

	dt = posting_datetime(posting_date, posting_time)
	row = frappe.get_doc(
		{
			"doctype": LEDGER,
			"company": company,
			"posting_date": posting_date,
			"posting_time": posting_time,
			"posting_datetime": dt,
			"item_code": item_code,
			"warehouse": warehouse,
			"zone": zone,
			"cost_center": cost_center,
			"wallet": wallet,
			"transaction_type": transaction_type,
			"transaction_doctype": doctype,
			"transaction_name": name,
			"transaction_detail_reference": detail,
			"source_key": source_key,
			"direction": direction,
			"qty_in": float(qty) if qty > 0 else 0,
			"qty_out": float(-qty) if qty < 0 else 0,
			"signed_qty": float(qty),
			"usd_rate": flt(usd_rate) if direction == "In" else 0,
			"btn_exchange_rate": flt(btn_rate),
			"market_usd_rate": flt(market_usd_rate) if direction == "Out" else 0,
		}
	)
	row.flags.ignore_permissions = True
	row.insert()
	rebuild(company, item_code, dt)
	return row.name


def reverse_source(doctype, name):
	"""Flag every live row of a source document as cancelled and rebuild the pool."""
	rows = frappe.get_all(
		LEDGER,
		filters={"transaction_doctype": doctype, "transaction_name": name, "is_cancelled": 0},
		fields=["name", "company", "item_code", "posting_datetime"],
	)
	for r in rows:
		frappe.db.set_value(LEDGER, r.name, {"is_cancelled": 1, "reversal_reference": f"Cancelled with {name}"})
	for key in {(r.company, r.item_code) for r in rows}:
		earliest = min(r.posting_datetime for r in rows if (r.company, r.item_code) == key)
		rebuild(key[0], key[1], earliest)


def rebuild(company, item_code, from_datetime):
	"""Recompute derived columns of live rows at/after from_datetime in posting order.

	Raises if any outgoing row would exceed the pool balance (a backdated receipt
	cancelled, or a backdated issue, that invalidates later history).
	"""
	prev = frappe.db.sql(
		"""select usd_balance_qty, usd_balance_value from `tabBTC USD Valuation Ledger`
		where company=%s and item_code=%s and is_cancelled=0 and posting_datetime < %s
		order by posting_datetime desc, creation desc, name desc limit 1""",
		(company, item_code, from_datetime),
	)
	bal_qty, bal_val = (D(prev[0][0]), D(prev[0][1])) if prev else (Decimal(0), Decimal(0))

	rows = frappe.db.sql(
		"""select name, direction, qty_in, qty_out, usd_rate, btn_exchange_rate, usd_incoming_value,
		usd_outgoing_value, market_usd_rate, usd_market_value, usd_market_difference, usd_balance_qty, usd_balance_value, usd_moving_average_rate, transaction_name
		from `tabBTC USD Valuation Ledger`
		where company=%s and item_code=%s and is_cancelled=0 and posting_datetime >= %s
		order by posting_datetime, creation, name""",
		(company, item_code, from_datetime),
		as_dict=True,
	)

	for r in rows:
		if r.direction == "In":
			qty = D(r.qty_in)
			rate = D(r.usd_rate)
			incoming, outgoing = _q(qty * rate, VAL_Q), Decimal(0)
			bal_qty, bal_val = _q(bal_qty + qty, QTY_Q), bal_val + incoming
			change = incoming
			avg = _q(bal_val / bal_qty, VAL_Q) if bal_qty else Decimal(0)
		else:
			qty = D(r.qty_out)
			if qty > bal_qty:
				frappe.throw(
					_("USD valuation: {0} issues {1} BTC but only {2} BTC is in the USD pool at that point.").format(
						r.transaction_name, qty, bal_qty
					),
					title=_("Insufficient BTC for USD valuation"),
				)
			avg_exact = bal_val / bal_qty
			avg = _q(avg_exact, VAL_Q)
			new_qty = _q(bal_qty - qty, QTY_Q)
			# Final unit out: take the whole remaining value so no rounding residue is left.
			outgoing = bal_val if new_qty == 0 else _q(qty * avg_exact, VAL_Q)
			incoming = Decimal(0)
			bal_qty, bal_val = new_qty, bal_val - outgoing
			change = -outgoing
			rate = avg

		values = {
			"usd_incoming_value": float(incoming),
			"usd_outgoing_value": float(outgoing),
			"usd_value_change": float(change),
			"usd_balance_qty": float(bal_qty),
			"usd_balance_value": float(bal_val),
			"usd_moving_average_rate": float(avg),
			"btn_value": float(_q((incoming or outgoing) * D(r.btn_exchange_rate), VAL_Q)),
		}
		if r.direction == "Out":
			values["usd_rate"] = float(rate)
			market = _q(qty * D(r.market_usd_rate), VAL_Q) if flt(r.market_usd_rate) else Decimal(0)
			values["usd_market_value"] = float(market)
			values["usd_market_difference"] = float(market - outgoing) if market else 0
		old = {k: flt(r.get(k), 9) for k in values}
		if any(flt(values[k], 9) != old[k] for k in values):
			values["last_recalculated_on"] = now_datetime()
			frappe.db.set_value(LEDGER, r.name, values, update_modified=False)


def get_usd_balance(company, item_code, as_of=None):
	"""Return (qty, value, average rate) of the live pool at as_of (default: now)."""
	as_of = as_of or now_datetime()
	row = frappe.db.sql(
		"""select usd_balance_qty, usd_balance_value, usd_moving_average_rate
		from `tabBTC USD Valuation Ledger`
		where company=%s and item_code=%s and is_cancelled=0 and posting_datetime <= %s
		order by posting_datetime desc, creation desc, name desc limit 1""",
		(company, item_code, as_of),
	)
	return tuple(flt(x, 9) for x in row[0]) if row else (0.0, 0.0, 0.0)


def reconcile(company, item_code):
	"""Compare the USD pool with the stock ledger; returns a dict with the differences."""
	qty, value, avg = get_usd_balance(company, item_code)
	sle_qty = flt(
		frappe.db.sql(
			"select coalesce(sum(actual_qty),0) from `tabStock Ledger Entry` where company=%s and item_code=%s and is_cancelled=0",
			(company, item_code),
		)[0][0],
		9,
	)
	return {"usd_pool_qty": qty, "usd_pool_value": value, "usd_avg_rate": avg, "stock_ledger_qty": sle_qty, "qty_difference": flt(qty - sle_qty, 9)}
