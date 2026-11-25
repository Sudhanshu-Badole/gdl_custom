"""Employee Separation phase 2: exit interview, confidential questionnaire and employee nomination.

All data is created inside the test and rolled back, so the site is left untouched.
"""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils import add_days

from gdl_custom_app.gdl_hr.exit_interview import create_exit_interview, service_band
from gdl_custom_app.gdl_hr.nomination import get_nomination_status
from gdl_custom_app.gdl_hr.report.exit_interview_answers.exit_interview_answers import execute as answers_report
from gdl_custom_app.tests.test_hr_separation_phase1 import SeparationBase


class Phase2Base(SeparationBase):
	def approved(self, **kw):
		"""A request approved by the supervisor and the CEO; the exit interview opens here."""
		doc = self.make_request(**kw)
		self.act(doc, "Submit for Approval", "emp")
		self.act(doc, "Approve", "sup")
		return self.act(doc, "Approve", "ceo")

	def exit_interview(self, request):
		request.reload()
		return frappe.get_doc("Exit Interview", request.exit_interview)

	def schedule(self, interview):
		frappe.set_user(self.users["hr"])
		interview.reload()
		interview.date = add_days(self.today, 5)
		interview.append("interviewers", {"user": self.users["hr"]})
		interview.status = "Scheduled"
		interview.save()
		interview.reload()
		return interview

	def answer_all(self, response, **overrides):
		"""Fill every row with the first option (or text) and apply per-question overrides by question text."""
		for row in response.answers:
			if row.question in overrides:
				row.answer = overrides[row.question]
			elif row.answer_type in ("Single Choice", "Rating 4", "Rating 5", "Multi Select"):
				row.answer = row.answer or row.options.splitlines()[0]
			else:
				row.answer = row.answer or "Answer"


class TestExitInterview(Phase2Base):
	def test_created_on_ceo_approval_and_linked(self):
		request = self.approved()
		interview = self.exit_interview(request)
		self.assertEqual(interview.status, "Pending")
		self.assertEqual(interview.employee, self.emp)
		self.assertEqual(interview.custom_separation_request, request.name)
		self.assertEqual(interview.custom_personal_email, "personal@example.com")
		self.assertEqual(interview.ref_doctype, "Separation Request")
		self.assertTrue(interview.relieving_date)
		self.assertTrue(interview.custom_service_band)

	def test_not_created_before_ceo_approval(self):
		request = self.make_request()
		self.act(request, "Submit for Approval", "emp")
		request.reload()
		self.assertFalse(request.exit_interview)

	def test_not_created_for_demise(self):
		request = self.approved(separation_type="Demise")
		request.reload()
		self.assertFalse(request.exit_interview)

	def test_only_one_interview_per_employee(self):
		request = self.approved()
		frappe.set_user("Administrator")
		self.assertEqual(create_exit_interview(request), request.exit_interview)
		self.assertEqual(frappe.db.count("Exit Interview", {"employee": self.emp, "docstatus": ["!=", 2]}), 1)

	def test_scheduling_needs_date_and_interviewers(self):
		interview = self.exit_interview(self.approved())
		frappe.set_user(self.users["hr"])
		interview.status = "Scheduled"
		with self.assertRaises(frappe.ValidationError):
			interview.save()

	def test_service_band(self):
		self.assertEqual(service_band("2026-06-01", "2026-09-01"), "Less than 6 months")
		self.assertEqual(service_band("2026-01-01", "2026-11-01"), "6 months - 1 year")
		self.assertEqual(service_band("2020-01-01", "2026-06-01"), "6-10 years")
		self.assertEqual(service_band("2010-01-01", "2026-06-01"), "more than 10 years")
		self.assertIsNone(service_band(None))


class TestQuestionnaire(Phase2Base):
	def response_for(self, request):
		interview = self.schedule(self.exit_interview(request))
		self.assertTrue(interview.custom_response)
		return interview, frappe.get_doc("Exit Interview Response", interview.custom_response)

	def test_template_has_the_annexure_1_parts(self):
		counts = dict(
			frappe.db.sql(
				"""select part, count(*) from `tabExit Interview Template Question`
				where parent = 'GDL Exit Interview' group by part"""
			)
		)
		self.assertEqual(len(counts), 7)
		self.assertEqual(counts["Part I: Employee Details"], 2)
		self.assertEqual(counts["Part VII: Supervisor"], 21)
		self.assertEqual(sum(counts.values()), 70)

	def test_scheduling_creates_the_employees_response_with_prefilled_part_one(self):
		interview, response = self.response_for(self.approved())
		self.assertEqual(response.owner, self.users["emp"])
		self.assertEqual(response.employee, self.emp)
		self.assertEqual(response.docstatus, 0)
		self.assertEqual(len(response.answers), 70)
		answers = {r.question: r.answer for r in response.answers}
		self.assertEqual(answers["Resignation Type"], "Voluntary Resignation")
		self.assertTrue(answers["How long have you worked in our company?"])
		self.assertEqual(
			frappe.db.count("Notification Log", {"for_user": self.users["emp"], "document_name": response.name}), 1
		)

	def test_scheduling_twice_gives_one_response(self):
		interview, response = self.response_for(self.approved())
		interview.save()
		self.assertEqual(frappe.db.count("Exit Interview Response", {"exit_interview": interview.name}), 1)

	def test_only_the_employee_and_hr_can_see_it(self):
		_interview, response = self.response_for(self.approved())
		for user, expected in (("emp", True), ("hr", True), ("sup", False), ("ceo", False), ("other", False)):
			frappe.set_user(self.users[user])
			self.assertEqual(bool(frappe.has_permission("Exit Interview Response", "read", response.name)), expected, user)
			if expected:
				self.assertIn(response.name, frappe.get_list("Exit Interview Response", pluck="name"), user)
			else:
				with self.assertRaises(frappe.PermissionError):
					frappe.get_doc("Exit Interview Response", response.name).check_permission("read")

	def test_employee_cannot_change_the_questions(self):
		_interview, response = self.response_for(self.approved())
		frappe.set_user(self.users["emp"])
		response.reload()
		response.answers[0].question = "Something else"
		with self.assertRaises(frappe.ValidationError):
			response.save()

	def test_answer_must_be_one_of_the_options(self):
		_interview, response = self.response_for(self.approved())
		frappe.set_user(self.users["emp"])
		response.reload()
		choice = next(r for r in response.answers if r.answer_type == "Single Choice")
		choice.answer = "Not an option"
		with self.assertRaises(frappe.ValidationError):
			response.save()

	def test_mandatory_questions_block_submit_then_it_submits(self):
		_interview, response = self.response_for(self.approved())
		frappe.set_user(self.users["emp"])
		response.reload()
		for row in response.answers:
			if not row.mandatory:
				row.answer = None
			elif row.answer_type == "Text":
				row.answer = None
		response.save()
		with self.assertRaises(frappe.ValidationError):
			response.submit()
		response.reload()
		self.answer_all(response)
		response.save()
		response.submit()
		self.assertEqual(response.docstatus, 1)

	def test_completed_needs_the_response_or_a_waiver(self):
		request = self.approved()
		interview, response = self.response_for(request)
		frappe.set_user(self.users["hr"])
		interview.reload()
		interview.status = "Completed"
		with self.assertRaises(frappe.ValidationError):
			interview.save()

		interview.reload()
		interview.status = "Completed"
		interview.custom_waive_reason = "Employee refused to complete the questionnaire"
		interview.save()  # a recorded waiver lets HR complete it
		interview.reload()
		interview.status = "Scheduled"
		interview.custom_waive_reason = None
		interview.save()

		frappe.set_user(self.users["emp"])
		response.reload()
		self.answer_all(response)
		response.save()
		response.submit()
		frappe.set_user(self.users["hr"])
		interview.reload()
		interview.status = "Completed"
		interview.save()  # a submitted response is enough
		self.assertEqual(frappe.db.get_value("Exit Interview", interview.name, "status"), "Completed")

	def test_hr_report_lists_submitted_answers_only(self):
		_interview, response = self.response_for(self.approved())
		frappe.set_user("Administrator")
		self.assertEqual(answers_report({"employee": self.emp})[1], [])
		frappe.set_user(self.users["emp"])
		response.reload()
		self.answer_all(response)
		response.save()
		response.submit()
		frappe.set_user("Administrator")
		rows = answers_report({"employee": self.emp})[1]
		self.assertEqual(len(rows), 70)
		self.assertEqual(len(answers_report({"employee": self.emp, "part": "Part VII"})[1]), 21)


class TestNomination(Phase2Base):
	def nominate(self, shares=(60, 40), user="emp", employee=None):
		frappe.set_user(self.users[user])
		doc = frappe.get_doc(
			{
				"doctype": "Employee Nomination",
				"employee": employee or self.emp,
				"nominees": [
					{"nominee_name": f"Nominee {i}", "relationship": "Spouse", "share_percent": share}
					for i, share in enumerate(shares, 1)
				],
			}
		).insert()
		return doc

	def test_status_missing_then_each_step(self):
		self.assertEqual(get_nomination_status(self.emp), "Missing")
		doc = self.nominate(shares=(60,))
		self.assertEqual(get_nomination_status(self.emp), "Total not 100%")
		doc.nominees[0].share_percent = 100
		doc.save()
		self.assertEqual(get_nomination_status(self.emp), "Not Verified")
		self.act(doc, "Submit Nomination", "emp")
		self.assertEqual(get_nomination_status(self.emp), "Not Verified")
		self.act(doc, "Verify", "hr")
		self.assertEqual(get_nomination_status(self.emp), "Valid")

	def test_total_must_be_100_to_submit(self):
		doc = self.nominate(shares=(60, 30))
		self.assertEqual(doc.total_share, 90)
		with self.assertRaises(frappe.ValidationError):
			self.act(doc, "Submit Nomination", "emp")

	def test_every_share_must_be_positive(self):
		with self.assertRaises(frappe.ValidationError):
			self.nominate(shares=(100, 0))

	def test_employee_files_only_their_own(self):
		with self.assertRaises((frappe.ValidationError, frappe.PermissionError)):
			self.nominate(employee=self.other_emp)

	def test_one_nomination_per_employee(self):
		self.nominate()
		with self.assertRaises(frappe.ValidationError):
			self.nominate()

	def test_verification_is_recorded(self):
		doc = self.nominate()
		self.act(doc, "Submit Nomination", "emp")
		doc = self.act(doc, "Verify", "hr")
		self.assertEqual(doc.verified_by, self.users["hr"])
		self.assertTrue(doc.verified_on)

	def test_only_hr_can_verify(self):
		doc = self.nominate()
		self.act(doc, "Submit Nomination", "emp")
		with self.assertRaises((frappe.ValidationError, frappe.PermissionError)):
			self.act(doc, "Verify", "emp")

	def test_return_to_draft_needs_a_reason(self):
		doc = self.nominate()
		self.act(doc, "Submit Nomination", "emp")
		frappe.set_user(self.users["hr"])
		doc.reload()
		with self.assertRaises(frappe.ValidationError):
			apply_workflow(doc, "Return to Draft")
		doc.reload()
		doc.remarks = "Share total does not match the signed form"
		doc.save()
		doc = apply_workflow(doc, "Return to Draft")
		self.assertEqual(doc.workflow_state, "Draft")
		self.assertEqual(get_nomination_status(self.emp), "Not Verified")

	def test_employee_cannot_edit_once_submitted(self):
		doc = self.nominate()
		self.act(doc, "Submit Nomination", "emp")
		frappe.set_user(self.users["emp"])
		doc.reload()
		doc.nominees[0].share_percent = 50
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_only_the_employee_and_hr_can_see_it(self):
		doc = self.nominate()
		for user, expected in (("emp", True), ("hr", True), ("sup", False), ("other", False)):
			frappe.set_user(self.users[user])
			self.assertEqual(bool(frappe.has_permission("Employee Nomination", "read", doc.name)), expected, user)


class TestAcknowledgeWarnsOnNomination(Phase2Base):
	def verified_nomination(self):
		frappe.set_user(self.users["emp"])
		doc = frappe.get_doc(
			{
				"doctype": "Employee Nomination",
				"employee": self.emp,
				"nominees": [{"nominee_name": "Spouse", "relationship": "Spouse", "share_percent": 100}],
			}
		).insert()
		self.act(doc, "Submit Nomination", "emp")
		self.act(doc, "Verify", "hr")

	def test_acknowledge_without_a_valid_nomination_needs_a_reason(self):
		request = self.approved()
		with self.assertRaises(frappe.ValidationError):
			self.act(request, "Acknowledge", "hr")
		frappe.set_user(self.users["hr"])
		request.reload()
		self.assertEqual(request.nomination_status, "Missing")
		request.nomination_reason = "Nomination form is with the employee's family; to follow"
		request.save()
		request = self.act(request, "Acknowledge", "hr")
		self.assertEqual(request.workflow_state, "HR Acknowledged")

	def test_acknowledge_with_a_valid_nomination_needs_no_reason(self):
		request = self.approved()
		self.verified_nomination()
		request = self.act(request, "Acknowledge", "hr")
		self.assertEqual(request.workflow_state, "HR Acknowledged")
		self.assertEqual(request.nomination_status, "Valid")

	def test_employee_separation_shows_the_interview_and_nomination(self):
		request = self.approved()
		self.verified_nomination()
		request = self.act(request, "Acknowledge", "hr")
		es = frappe.get_doc("Employee Separation", request.employee_separation)
		self.assertEqual(es.custom_exit_interview, request.exit_interview)
		self.assertEqual(es.custom_nomination_status, "Valid")
