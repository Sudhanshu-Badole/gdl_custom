"""Employee Separation phase 3: Full and Final Statement, benefit formulas, recoveries, checks and print format.

All data is created inside the test and rolled back, so the site is left untouched.
"""

import frappe
from frappe.utils import date_diff, flt

from gdl_custom_app.gdl_hr import fnf
from gdl_custom_app.tests.test_hr_separation_phase1 import make_user
from gdl_custom_app.tests.test_hr_separation_phase2 import Phase2Base


def make_benefit(name, section, formula, **kw):
	return frappe.get_doc(
		{
			"doctype": "Separation Benefit Type",
			"benefit_name": name,
			"section": section,
			"formula": formula,
			"is_active": 1,
			**kw,
		}
	).insert(ignore_permissions=True)


class Phase3Base(Phase2Base):
	def complete_interview(self, request):
		interview = self.exit_interview(request)
		frappe.set_user(self.users["hr"])
		interview.reload()
		interview.status = "Completed"
		interview.employee_status = "Exit Confirmed"
		interview.custom_waive_reason = "Completed without the questionnaire in this test"
		interview.save()

	def statement(self, request, user="hr"):
		frappe.set_user(self.users[user])
		doc = frappe.get_doc(
			{
				"doctype": "Full and Final Statement",
				"employee": request.employee,
				"company": "GreenDigital Limited",
				"transaction_date": str(self.today),
				"relieving_date": frappe.db.get_value("Employee", request.employee, "relieving_date"),
			}
		)
		doc.insert()
		return doc

	def ready(self, **kw):
		"""A CEO-approved request whose exit interview is Completed, plus an F&F ready to be created."""
		request = self.approved(**kw)
		self.complete_interview(request)
		return request

	def rows(self, doc, table):
		return {r.custom_benefit_type: r for r in doc.get(table) if r.custom_benefit_type}


class TestCreationChecks(Phase3Base):
	def test_blocked_until_exit_interview_completed(self):
		request = self.approved()
		with self.assertRaises(frappe.ValidationError):
			self.statement(request)
		self.complete_interview(request)
		self.assertTrue(self.statement(request).name)

	def test_demise_skips_the_interview_check(self):
		request = self.approved(separation_type="Demise")
		doc = self.statement(request)
		self.assertEqual(doc.custom_separation_type, "Demise")

	def test_employee_outside_the_process_is_not_affected(self):
		frappe.set_user("Administrator")
		frappe.db.set_value("Employee", self.other_emp, "relieving_date", str(self.today))
		doc = frappe.get_doc(
			{
				"doctype": "Full and Final Statement",
				"employee": self.other_emp,
				"company": "GreenDigital Limited",
				"transaction_date": str(self.today),
				"relieving_date": str(self.today),
			}
		)
		doc.insert()
		self.assertFalse(doc.custom_separation_request)

	def test_statement_is_linked_to_the_process(self):
		request = self.ready()
		doc = self.statement(request)
		self.assertEqual(doc.custom_separation_request, request.name)
		self.assertEqual(doc.custom_exit_interview, request.exit_interview)
		self.assertEqual(doc.custom_separation_type, "Voluntary resignation")

	def test_start_from_the_request(self):
		request = self.ready()
		self.to_hr_acknowledged_after_approval(request)
		frappe.set_user(self.users["hr"])
		name = fnf.start_full_and_final(request.name)
		self.assertEqual(frappe.db.get_value("Separation Request", request.name, "full_and_final_statement"), name)
		self.assertEqual(fnf.start_full_and_final(request.name), name)  # a second click opens the same one

	def test_only_hr_can_start(self):
		request = self.ready()
		self.to_hr_acknowledged_after_approval(request)
		frappe.set_user(self.users["emp"])
		with self.assertRaises(frappe.PermissionError):
			fnf.start_full_and_final(request.name)

	def test_start_needs_hr_acknowledged(self):
		request = self.ready()
		frappe.set_user(self.users["hr"])
		with self.assertRaises(frappe.ValidationError):
			fnf.start_full_and_final(request.name)

	def to_hr_acknowledged_after_approval(self, request):
		frappe.db.set_value("Separation Request", request.name, "nomination_reason", "No nomination in this test")
		return self.act(request, "Acknowledge", "hr")


class TestBenefits(Phase3Base):
	def test_formulas_fill_sections_and_totals(self):
		make_benefit("T Gratuity", fnf.SECTION_BENEFITS, "completed_years * 1000 + 500")
		make_benefit("T Transfer", fnf.SECTION_BENEFITS, "2000")
		make_benefit("T Notice", fnf.SECTION_RECOVERIES, "notice_shortfall_days * 100")
		request = self.ready(last_working_date=str(frappe.utils.add_days(self.today, 20)))
		doc = self.statement(request)

		doj, relieving = frappe.db.get_value("Employee", self.emp, ["date_of_joining", "relieving_date"])
		years = int(date_diff(relieving, doj) / 30.4375 // 12)
		payables, receivables = self.rows(doc, "payables"), self.rows(doc, "receivables")
		self.assertEqual(payables["T Gratuity"].amount, years * 1000 + 500)
		self.assertEqual(payables["T Gratuity"].custom_section, fnf.SECTION_BENEFITS)
		self.assertEqual(payables["T Transfer"].amount, 2000)
		self.assertEqual(receivables["T Notice"].amount, 1000)  # 10 days short x 100
		self.assertEqual(receivables["T Notice"].custom_section, fnf.SECTION_RECOVERIES)
		self.assertEqual(doc.custom_total_benefits, years * 1000 + 2500)
		self.assertEqual(doc.custom_total_recoveries, 1000)
		self.assertEqual(doc.custom_net_payable, years * 1000 + 2500 - 1000)

	def test_zero_amount_is_skipped_unless_always_add(self):
		make_benefit("T Zero", fnf.SECTION_BENEFITS, "0")
		make_benefit("T Zero Kept", fnf.SECTION_BENEFITS, "0", mandatory=1)
		doc = self.statement(self.ready())
		rows = self.rows(doc, "payables")
		self.assertNotIn("T Zero", rows)
		self.assertIn("T Zero Kept", rows)

	def test_inactive_types_are_ignored(self):
		make_benefit("T Off", fnf.SECTION_BENEFITS, "9999", is_active=0)
		self.assertNotIn("T Off", self.rows(self.statement(self.ready()), "payables"))

	def test_applies_only_to_listed_separation_types(self):
		make_benefit("T Retrench", fnf.SECTION_BENEFITS, "7000", applicable_types=[{"separation_type": "Retrenchment"}])
		make_benefit("T Everyone", fnf.SECTION_BENEFITS, "100")
		rows = self.rows(self.statement(self.ready()), "payables")  # a voluntary resignation
		self.assertNotIn("T Retrench", rows)
		self.assertIn("T Everyone", rows)

	def test_unknown_value_in_a_formula_is_a_clear_error(self):
		make_benefit("T Broken", fnf.SECTION_BENEFITS, "BS * 2")  # the employee has no salary slip
		request = self.ready()
		with self.assertRaises(frappe.ValidationError) as ctx:
			self.statement(request)
		self.assertIn("T Broken", str(ctx.exception))

	def test_formula_cannot_run_code(self):
		make_benefit("T Evil", fnf.SECTION_BENEFITS, "__import__('os').getcwd()")
		with self.assertRaises(frappe.ValidationError):
			self.statement(self.ready())

	def test_rows_use_the_benefit_account_when_given(self):
		account = frappe.db.get_value("Account", {"company": "GreenDigital Limited", "is_group": 0, "root_type": "Expense"}, "name")
		if not account:
			self.skipTest("no expense account")
		make_benefit("T Account", fnf.SECTION_BENEFITS, "100", account=account)
		self.assertEqual(self.rows(self.statement(self.ready()), "payables")["T Account"].account, account)

	def test_recalculate_replaces_unsettled_rows(self):
		benefit = make_benefit("T Recalc", fnf.SECTION_BENEFITS, "100")
		doc = self.statement(self.ready())
		self.assertEqual(self.rows(doc, "payables")["T Recalc"].amount, 100)
		benefit.formula = "250"
		benefit.save()
		frappe.set_user(self.users["hr"])
		fnf.recalculate_benefits(doc.name)
		doc.reload()
		self.assertEqual(self.rows(doc, "payables")["T Recalc"].amount, 250)
		self.assertEqual(len([r for r in doc.payables if r.custom_benefit_type == "T Recalc"]), 1)

	def test_settled_rows_survive_a_recalculation(self):
		make_benefit("T Settled", fnf.SECTION_BENEFITS, "100")
		doc = self.statement(self.ready())
		for row in doc.payables:
			row.status = "Settled"
		doc.save()
		frappe.db.set_value("Separation Benefit Type", "T Settled", "formula", "999")
		fnf.recalculate_benefits(doc.name)
		doc.reload()
		self.assertEqual(self.rows(doc, "payables")["T Settled"].amount, 100)

	def test_empty_hrms_placeholder_rows_are_dropped(self):
		doc = self.statement(self.ready())
		self.assertEqual([r for r in doc.payables if not r.custom_benefit_type and not r.reference_document], [])
		self.assertEqual([r for r in doc.receivables if not r.custom_benefit_type and not r.reference_document], [])

	def test_rows_added_by_hand_get_a_section(self):
		doc = self.statement(self.ready())
		doc.append("payables", {"component": "Gratuity", "reference_document_type": "Gratuity", "status": "Settled", "amount": 1})
		doc.append("payables", {"component": "Expense Claim", "reference_document_type": "Expense Claim", "status": "Settled", "amount": 1})
		doc.append("receivables", {"component": "Employee Advance", "reference_document_type": "Employee Advance", "status": "Settled", "amount": 1})
		fnf.before_validate(doc)
		sections = {r.component: r.custom_section for r in [*doc.payables, *doc.receivables]}
		self.assertEqual(sections["Gratuity"], fnf.SECTION_BENEFITS)
		self.assertEqual(sections["Expense Claim"], fnf.SECTION_EARNED)
		self.assertEqual(sections["Employee Advance"], fnf.SECTION_RECOVERIES)

	def test_training_bond_ratio(self):
		emp = frappe._dict(
			custom_bond_amount=1000, custom_bond_start_date="2026-01-01", custom_bond_end_date="2027-01-01"
		)
		self.assertAlmostEqual(fnf.bond_unserved_ratio(emp, frappe.utils.getdate("2026-07-02")), 183 / 365, places=3)
		self.assertEqual(fnf.bond_unserved_ratio(emp, frappe.utils.getdate("2027-06-01")), 0)
		self.assertEqual(fnf.bond_unserved_ratio(frappe._dict(custom_bond_amount=0), frappe.utils.getdate("2026-07-02")), 0)

	def test_bond_recovery_uses_the_employee_bond(self):
		frappe.db.set_value(
			"Employee",
			self.emp,
			{
				"custom_bond_amount": 10000,
				"custom_bond_start_date": frappe.utils.add_days(self.today, -100),
				"custom_bond_end_date": frappe.utils.add_days(self.today, 265),
			},
		)
		make_benefit("T Bond", fnf.SECTION_RECOVERIES, "round(bond_amount * bond_unserved_ratio)")
		doc = self.statement(self.ready())
		amount = self.rows(doc, "receivables")["T Bond"].amount
		self.assertTrue(5000 < amount < 10000)

	def test_starting_list_is_inactive_and_has_every_type(self):
		for name in ("Gratuity", "Transfer Grant", "Notice Shortfall Recovery", "STTP Bond Refund", "LTTP Refund"):
			self.assertEqual(frappe.db.get_value("Separation Benefit Type", name, "is_active"), 0)
		self.assertEqual(frappe.db.count("Separation Benefit Type", {"benefit_name": ["like", "%"]}) >= 15, True)


class TestPayees(Phase3Base):
	def verified_nomination(self):
		frappe.set_user(self.users["emp"])
		nomination = frappe.get_doc(
			{
				"doctype": "Employee Nomination",
				"employee": self.emp,
				"nominees": [
					{"nominee_name": "Spouse One", "relationship": "Spouse", "share_percent": 60},
					{"nominee_name": "Child One", "relationship": "Child", "share_percent": 40},
				],
			}
		).insert()
		self.act(nomination, "Submit Nomination", "emp")
		self.act(nomination, "Verify", "hr")

	def test_employee_is_the_only_payee_on_resignation(self):
		make_benefit("T Pay", fnf.SECTION_BENEFITS, "10000")
		doc = self.statement(self.ready())
		self.assertEqual(len(doc.custom_payees), 1)
		self.assertEqual(doc.custom_payees[0].nominee_name, doc.employee_name)
		self.assertEqual(doc.custom_payees[0].amount, 10000)

	def test_nominees_share_the_net_amount_on_demise(self):
		self.verified_nomination()
		make_benefit("T Pay", fnf.SECTION_BENEFITS, "10000")
		doc = self.statement(self.approved(separation_type="Demise"))
		payees = {p.nominee_name: p for p in doc.custom_payees}
		self.assertEqual(payees["Spouse One"].amount, 6000)
		self.assertEqual(payees["Child One"].amount, 4000)
		self.assertEqual(sum(flt(p.share_percent) for p in doc.custom_payees), 100)

	def test_negative_net_pays_nobody(self):
		make_benefit("T Owe", fnf.SECTION_RECOVERIES, "500")
		doc = self.statement(self.ready())
		self.assertEqual(doc.custom_net_payable, -500)
		self.assertEqual(doc.custom_payees[0].amount, 0)

	def test_demise_without_valid_nomination_needs_a_reason(self):
		doc = frappe._dict(employee=self.emp, custom_separation_type="Demise", custom_nomination_reason=None)
		with self.assertRaises(frappe.ValidationError):
			fnf.check_nomination(doc)
		doc.custom_nomination_reason = "Heirs named by court order"
		fnf.check_nomination(doc)

	def test_resignation_does_not_need_a_nomination_to_submit(self):
		doc = frappe._dict(employee=self.emp, custom_separation_type="Voluntary resignation", custom_nomination_reason=None)
		fnf.check_nomination(doc)  # rule 7 is a warning at HR Acknowledge, not a payment block

	def test_nomination_valid_lets_a_demise_proceed(self):
		self.verified_nomination()
		doc = frappe._dict(employee=self.emp, custom_separation_type="Demise", custom_nomination_reason=None)
		fnf.check_nomination(doc)


class TestSubmitRules(Phase3Base):
	def acknowledged(self):
		request = self.ready()
		frappe.db.set_value("Separation Request", request.name, "nomination_reason", "No nomination in this test")
		self.act(request, "Acknowledge", "hr")
		request.reload()
		return request

	def submit_separation(self, request):
		frappe.set_user("Administrator")
		holiday_list = frappe.db.get_value(
			"Holiday List", {"from_date": ["<=", self.today]}, ["name", "from_date"], as_dict=True
		)
		if not holiday_list:
			self.skipTest("no Holiday List covering today")
		frappe.get_doc(
			{
				"doctype": "Holiday List Assignment",
				"applicable_for": "Employee",
				"assigned_to": self.emp,
				"holiday_list": holiday_list.name,
				"from_date": holiday_list.from_date,
			}
		).insert(ignore_permissions=True).submit()
		es = frappe.get_doc("Employee Separation", request.employee_separation)
		es.submit()
		return es

	def settle_all(self, doc):
		for table in ("payables", "receivables"):
			for row in doc.get(table):
				row.status = "Settled"
		doc.save()

	def test_blocked_while_the_separation_record_is_not_submitted(self):
		request = self.acknowledged()
		doc = self.statement(request)
		self.settle_all(doc)
		with self.assertRaises(frappe.ValidationError) as ctx:
			doc.submit()
		self.assertIn("not submitted", str(ctx.exception))

	def test_blocked_while_a_clearance_item_is_open(self):
		request = self.acknowledged()
		es = self.submit_separation(request)
		tasks = frappe.get_all("Employee Boarding Activity", filters={"parent": es.name, "task": ["is", "set"]}, pluck="task")
		frappe.db.set_value("Employee Separation", es.name, "custom_clearance_attachment", "/files/signoff.pdf")
		for task in tasks[:-1]:
			frappe.db.set_value("Task", task, "status", "Completed")
		doc = self.statement(request)
		self.settle_all(doc)
		with self.assertRaises(frappe.ValidationError):
			doc.submit()
		self.assertEqual(len(fnf.open_clearance_items(es.name)), 1)

	def test_submits_when_clearance_is_complete(self):
		request = self.acknowledged()
		es = self.submit_separation(request)
		tasks = frappe.get_all("Employee Boarding Activity", filters={"parent": es.name, "task": ["is", "set"]}, pluck="task")
		for task in tasks:
			frappe.db.set_value("Task", task, "status", "Completed")
		doc = self.statement(request)
		self.settle_all(doc)
		doc.submit()
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(fnf.open_clearance_items(es.name), [])

		# Finance (read only) builds the journal entry through the dedicated method; the employee cannot
		finance = make_user("sep.fin2@example.com", ["Employee", "Accounts User"])
		frappe.set_user(finance)
		self.assertEqual(fnf.create_journal_entry(doc.name)["doctype"], "Journal Entry")
		frappe.set_user(self.users["emp"])
		with self.assertRaises(frappe.PermissionError):
			fnf.create_journal_entry(doc.name)

	def test_calculated_rows_need_an_account(self):
		make_benefit("T NoAccount", fnf.SECTION_BENEFITS, "100")
		request = self.acknowledged()
		es = self.submit_separation(request)
		for task in frappe.get_all("Employee Boarding Activity", filters={"parent": es.name, "task": ["is", "set"]}, pluck="task"):
			frappe.db.set_value("Task", task, "status", "Completed")
		doc = self.statement(request)
		self.settle_all(doc)
		with self.assertRaises(frappe.ValidationError) as ctx:
			doc.submit()
		self.assertIn("Account", str(ctx.exception))


class TestAccessAndPrint(Phase3Base):
	def test_finance_can_read_but_the_employee_cannot(self):
		doc = self.statement(self.ready())
		finance = make_user("sep.fin@example.com", ["Employee", "Accounts User"])
		self.assertTrue(frappe.has_permission("Full and Final Statement", "read", doc=doc, user=finance))
		self.assertFalse(frappe.has_permission("Full and Final Statement", "write", doc=doc, user=finance))
		self.assertFalse(frappe.has_permission("Full and Final Statement", "create", user=finance))
		self.assertFalse(frappe.has_permission("Full and Final Statement", "submit", doc=doc, user=finance))
		self.assertFalse(frappe.has_permission("Full and Final Statement", "read", doc=doc, user=self.users["emp"]))

	def test_benefit_types_are_hr_only_to_edit(self):
		self.assertTrue(frappe.has_permission("Separation Benefit Type", "write", user=self.users["hr"]))
		self.assertFalse(frappe.has_permission("Separation Benefit Type", "read", user=self.users["emp"]))

	def test_print_format_follows_the_a_to_f_layout(self):
		make_benefit("T Printed", fnf.SECTION_BENEFITS, "1234")
		doc = self.statement(self.ready())
		html = frappe.get_print("Full and Final Statement", doc.name, "GDL Full and Final Statement")
		for heading in ("A. Earned Pay", "B. Separation Benefits", "C. Recoveries", "D. Statutory", "E. Net Payable", "F. Paid Outside"):
			self.assertIn(heading, html)
		self.assertIn("T Printed", html)
		order = [html.index(h) for h in ("A. Earned Pay", "B. Separation Benefits", "C. Recoveries", "E. Net Payable")]
		self.assertEqual(order, sorted(order))

	def test_notification_to_finance_is_set_up(self):
		doc = frappe.get_doc("Notification", "Full and Final Statement - Submitted")
		self.assertEqual(doc.event, "Submit")
		self.assertEqual([r.receiver_by_role for r in doc.recipients], ["Accounts Manager"])


class TestReports(Phase3Base):
	def run_report(self, name, **filters):
		from frappe.desk.query_report import run

		frappe.set_user("Administrator")
		return run(name, filters=frappe._dict(filters))["result"]

	def test_separation_summary_counts_by_type_and_state(self):
		self.approved()
		rows = self.run_report("Separation Summary", separation_type="Voluntary resignation")
		row = [r for r in rows if r["workflow_state"] == "Approved by CEO"][0]
		self.assertEqual(row["requests"], 1)

	def test_pending_report_shows_what_is_holding_the_statement(self):
		request = self.approved()
		rows = {r["request"]: r for r in self.run_report("Full and Final Pending")}
		self.assertIn("Exit interview", rows[request.name]["waiting_for"])
		self.assertEqual(rows[request.name]["nomination"], "Missing")
		self.complete_interview(request)
		self.statement(request)
		rows = {r["request"]: r for r in self.run_report("Full and Final Pending")}
		self.assertIn("Statement in draft", rows[request.name]["waiting_for"])
		self.assertNotIn("Exit interview", rows[request.name]["waiting_for"])

	def test_benefit_report_totals_by_component(self):
		make_benefit("T Report", fnf.SECTION_BENEFITS, "1500")
		self.statement(self.ready())
		rows = self.run_report("Benefit and Recovery", include_drafts=1, section=fnf.SECTION_BENEFITS)
		row = [r for r in rows if r["component"] == "T Report"][0]
		self.assertEqual(row["amount"], 1500)
		self.assertEqual(row["section"], fnf.SECTION_BENEFITS)

	def test_nomination_gaps_lists_separating_employees_only_by_default(self):
		request = self.approved()
		names = [r["employee"] for r in self.run_report("Nomination Gaps")]
		self.assertEqual(names, [self.emp])
		self.assertIn(self.other_emp, [r["employee"] for r in self.run_report("Nomination Gaps", all_employees=1)])
