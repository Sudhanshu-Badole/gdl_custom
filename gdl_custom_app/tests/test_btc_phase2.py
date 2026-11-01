import frappe
from frappe.utils import flt

from gdl_custom_app.gdl_custom_app.doctype.btc_restriction import btc_restriction as br
from gdl_custom_app.tests import btc_test_utils as u
from gdl_custom_app.tests.test_btc_phase1 import BTCPhase1Base


class TestTransferFee(BTCPhase1Base):
	def setUp(self):
		super().setUp()
		u.set_settings(fee_expense_account=u.DIFFERENCE_ACCOUNT)

	def _fee_transfer(self, **kw):
		u.make_receipt(qty=1, usd_rate=50800, date=u.D1)
		return u.make_transfer(0.5, fee_qty=0.001, fee_rate=61000, **kw)

	def test_d09_e01_fee_quantities(self):
		self._fee_transfer()
		self.assertClose(u.wallet_balance(u.WALLET_A), 1 - 0.501, 9)
		self.assertClose(u.wallet_balance(u.WALLET_B), 0.5, 9)
		total = u.wallet_balance(u.WALLET_A) + u.wallet_balance(u.WALLET_B)
		self.assertClose(total, 0.999, 9)

	def test_e02_e03_scenario3_fee_cost_market_difference(self):
		se = self._fee_transfer()
		fee = u.ledger(direction="Out")[0]
		self.assertClose(fee.usd_outgoing_value, 50.80)
		self.assertClose(fee.usd_market_value, 61.00)
		self.assertClose(fee.usd_market_difference, 10.20)
		self.assertEqual(fee.transaction_doctype, "Stock Entry")
		self.assertNotEqual(fee.transaction_name, se.name)  # posted by the linked fee issue
		self.assertEqual((fee.zone, fee.wallet), (u.ZONE_A, u.WALLET_A))  # e04 same source dimensions
		self.assertEqual(u.pool()[0], 0.999)

	def test_fee_gl_posted_once(self):
		se = self._fee_transfer()
		issue = frappe.db.get_value("Stock Entry", se.name, "custom_fee_stock_entry")
		gl = frappe.get_all("GL Entry", filters={"voucher_no": issue, "is_cancelled": 0}, fields=["account", "debit", "credit"])
		self.assertEqual(len(gl), 2)
		self.assertClose(sum(g.debit for g in gl), 0.001 * 50800 * 90)  # BTN at moving-average cost
		self.assertEqual(frappe.get_all("GL Entry", filters={"voucher_no": se.name, "is_cancelled": 0}), [])  # neutral transfer

	def test_e05_fee_pushes_over_balance(self):
		u.make_receipt(qty=0.5, date=u.D1)
		with self.assertRaises(frappe.ValidationError):
			u.make_transfer(0.5, fee_qty=0.001, fee_rate=61000)

	def test_e06_zero_fee_creates_no_issue(self):
		u.make_receipt(qty=1, date=u.D1)
		se = u.make_transfer(0.5)
		self.assertFalse(frappe.db.get_value("Stock Entry", se.name, "custom_fee_stock_entry"))
		self.assertEqual(u.ledger(direction="Out"), [])

	def test_e07_negative_fee(self):
		u.make_receipt(qty=1, date=u.D1)
		with self.assertRaises(frappe.ValidationError):
			u.make_transfer(0.5, fee_qty=-0.001, fee_rate=61000)

	def test_e08_d10_cancel_reverses_fee(self):
		se = self._fee_transfer()
		se.cancel()
		self.assertClose(u.wallet_balance(u.WALLET_A), 1, 9)
		self.assertClose(u.wallet_balance(u.WALLET_B), 0, 9)
		self.assertTrue(all(r.is_cancelled for r in u.ledger(direction="Out")))
		self.assertEqual(u.pool()[:2], (1, 50800))

	def test_ui_cancel_dialog_sees_no_blocking_links(self):
		# The Desk "Cancel" button asks which submitted documents link to this one and cancels
		# them first; a fee issue that links back used to make that impossible.
		from frappe.desk.form.linked_with import get_submitted_linked_docs

		se = self._fee_transfer()
		linked = get_submitted_linked_docs("Stock Entry", se.name).get("docs") or []
		self.assertEqual([d for d in linked if d.get("doctype") == "Stock Entry"], [])

	def test_self_transfer_rejected(self):
		u.make_receipt(qty=1, date=u.D1)
		with self.assertRaises(frappe.ValidationError):
			u.make_transfer(0.1, to_wallet=u.WALLET_A)


class TestRestrictions(BTCPhase1Base):
	def setUp(self):
		super().setUp()
		u.make_receipt(qty=1, usd_rate=50000, date=u.D1)

	def test_f01_available_btc_can_move(self):
		u.make_transfer(0.6)
		self.assertClose(u.wallet_balance(u.WALLET_B), 0.6, 9)

	def test_f02_f03_f04_all_restriction_types_block(self):
		for kind in ("Trading", "Loan", "Pledged"):
			r = u.make_restriction(0.4, kind)
			with self.assertRaises(frappe.ValidationError):
				u.make_transfer(0.7)
			frappe.delete_doc("BTC Restriction", r.name, force=True, ignore_permissions=True) if False else frappe.db.set_value("BTC Restriction", r.name, "state", "Cancelled")

	def test_f09_partial_restriction_leaves_rest_usable(self):
		u.make_restriction(0.4)
		with self.assertRaises(frappe.ValidationError):
			u.make_issue(0.4 + 0.3)  # 0.7 > 0.6 unrestricted
		u.make_issue(0.6)  # exactly the unrestricted portion
		self.assertClose(u.wallet_balance(u.WALLET_A), 0.4, 9)

	def test_f10_over_allocation(self):
		with self.assertRaises(frappe.ValidationError):
			u.make_restriction(1.5)

	def test_f11_duplicate_restriction(self):
		u.make_restriction(0.7)
		with self.assertRaises(frappe.ValidationError):
			u.make_restriction(0.5)

	def test_scenario4_release_then_sell(self):
		r = u.make_restriction(0.4, "Pledged")
		with self.assertRaises(frappe.ValidationError):
			u.make_issue(0.7)
		br.release_restriction(r.name, 0.4, "Loan repaid")
		r.reload()
		self.assertEqual((r.state, r.released_qty, r.remaining_qty), ("Released", 0.4, 0))
		u.make_issue(0.7)  # now allowed

	def test_f05_f06_f12_expiry_boundary_and_idempotency(self):
		r = u.make_restriction(0.4, expiry=u.D3)
		self.assertEqual(br.expire_restrictions(u.D3), [])  # expiry day itself: still restricted
		with self.assertRaises(frappe.ValidationError):
			u.make_issue(0.7, date=u.D3)
		self.assertEqual(br.expire_restrictions(u.D4), [r.name])  # day after: released
		self.assertEqual(br.expire_restrictions(u.D4), [])  # rerun: nothing
		r.reload()
		self.assertEqual((r.state, len(r.release_log), r.release_log[0].kind), ("Expired", 1, "Expiry"))
		u.make_issue(0.7, date=u.D4)

	def test_f07_unauthorized_release(self):
		r = u.make_restriction(0.4)
		if not frappe.db.exists("User", "btc-noperm@example.com"):
			frappe.get_doc({"doctype": "User", "email": "btc-noperm@example.com", "first_name": "NoPerm",
				"send_welcome_email": 0, "roles": [{"role": "Stock User"}]}).insert(ignore_permissions=True)
		frappe.set_user("btc-noperm@example.com")
		with self.assertRaises(frappe.PermissionError):
			br.release_restriction(r.name, 0.1, "no")

	def test_f08_authorized_release_is_audited(self):
		r = u.make_restriction(0.4)
		br.release_restriction(r.name, 0.1, "Margin call cleared")
		r.reload()
		log = r.release_log[0]
		self.assertEqual((log.kind, log.qty, log.released_by, log.reason), ("Early Release", 0.1, "Administrator", "Margin call cleared"))
		self.assertTrue(log.released_on)
		self.assertEqual((r.state, r.remaining_qty), ("Active", 0.3))
		with self.assertRaises(frappe.ValidationError):
			br.release_restriction(r.name, 0.1, "")  # reason mandatory

	def test_direct_edit_of_protected_fields_blocked(self):
		r = u.make_restriction(0.4)
		r.qty = 0.1
		with self.assertRaises(frappe.ValidationError):
			r.save()

	def test_f13_extension_keeps_history_and_not_released_on_old_date(self):
		old, new = "2026-11-15", "2026-11-20"  # future-dated: extension is refused once expired
		r = u.make_restriction(0.4, expiry=old)
		br.extend_restriction(r.name, new, "Rolled")
		self.assertEqual(br.expire_restrictions("2026-11-16"), [])  # old expiry passed, still active
		r.reload()
		self.assertEqual((str(r.original_expiry_date), str(r.expiry_date)), (old, new))
		self.assertEqual(str(r.extension_log[0].previous_expiry), old)
		with self.assertRaises(frappe.ValidationError):
			br.extend_restriction(r.name, old, "back")
		self.assertEqual(br.expire_restrictions("2026-11-21"), [r.name])

	def test_transfer_with_status_creates_restriction_and_cancel_cancels_it(self):
		se = u.make_transfer(0.5, status="Trading", expiry=u.D4)
		r = frappe.get_doc("BTC Restriction", {"source_name": se.name})
		self.assertEqual((r.wallet, r.zone, r.qty, r.state), (u.WALLET_B, u.ZONE_A, 0.5, "Active"))
		with self.assertRaises(frappe.ValidationError):  # B's 0.5 BTC is all restricted
			u.make_issue(0.1, wallet=u.WALLET_B, date=u.D4)
		se.cancel()
		self.assertEqual(frappe.db.get_value("BTC Restriction", r.name, "state"), "Cancelled")

	def test_status_needs_expiry(self):
		with self.assertRaises(frappe.ValidationError):
			u.make_transfer(0.5, status="Loan")
		with self.assertRaises(frappe.ValidationError):
			u.make_transfer(0.5, status="Available", expiry=u.D4)

	def test_f_cancelled_restriction_stops_restricting(self):
		se = u.make_transfer(0.5, status="Pledged", expiry=u.D4)
		se.cancel()
		self.assertClose(u.wallet_balance(u.WALLET_A), 1, 9)
