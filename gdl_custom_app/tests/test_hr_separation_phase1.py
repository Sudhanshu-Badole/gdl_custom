"""Employee Separation phase 1: request, workflow, locking, Employee Separation creation, closure.

All data is created inside the test and rolled back, so the site is left untouched.
"""

import frappe
from unittest import mock

from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, nowdate

from gdl_custom_app.gdl_hr import closure
from gdl_custom_app.gdl_hr.separation import DEMISE_ACTIVITY

COMPANY = "GreenDigital Limited"
PASSWORD_USERS = {
	"emp": ("sep.emp@example.com", ["Employee"]),
	"sup": ("sep.sup@example.com", ["Employee"]),
	"other": ("sep.other@example.com", ["Employee"]),
	"ceo": ("sep.ceo@example.com", ["Employee", "CEO"]),
	"hr": ("sep.hr@example.com", ["Employee", "HR Manager", "HR User"]),
}


def make_user(email, roles):
	user = frappe.get_doc(
		{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
	)
	user.insert(ignore_permissions=True)
	user.add_roles(*roles)
	return email


def make_employee(first_name, user=None, reports_to=None, employment_type="Full-time", **extra):
	doc = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": first_name,
			"gender": "Male",
			"date_of_birth": "1990-01-01",
			"date_of_joining": "2020-01-01",
			"company": COMPANY,
			"status": "Active",
			"user_id": user,
			"reports_to": reports_to,
			"employment_type": employment_type,
			**extra,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


class SeparationBase(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.users = {k: make_user(*v) for k, v in PASSWORD_USERS.items()}
		self.sup_emp = make_employee("SepSup", self.users["sup"])
		self.emp = make_employee("SepEmp", self.users["emp"], reports_to=self.sup_emp)
		self.other_emp = make_employee("SepOther", self.users["other"])
		self.today = getdate(nowdate())

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def make_request(self, employee=None, user="emp", **kw):
		frappe.set_user(self.users[user])
		doc = frappe.get_doc(
			{
				"doctype": "Separation Request",
				"employee": employee or self.emp,
				"separation_type": "Voluntary resignation",
				"resignation_date": str(self.today),
				"last_working_date": str(add_days(self.today, 30)),
				"personal_email": "personal@example.com",
				"reason_for_leaving": "Better opportunity",
				"handover_status": "Not Started",
				**kw,
			}
		).insert()
		return doc

	def act(self, doc, action, user):
		frappe.set_user(self.users[user])
		doc.reload()
		return apply_workflow(doc, action)

	def to_hr_acknowledged(self, doc):
		self.act(doc, "Submit for Approval", "emp")
		self.act(doc, "Approve", "sup")
		self.act(doc, "Approve", "ceo")
		# rule 7 warns when there is no valid nomination: HR records why it proceeds
		frappe.db.set_value("Separation Request", doc.name, "nomination_reason", "No nomination on file in this test")
		return self.act(doc, "Acknowledge", "hr")


class TestRequestRules(SeparationBase):
	def test_notice_and_shortfall(self):
		doc = self.make_request(last_working_date=str(add_days(self.today, 20)))
		self.assertEqual(doc.notice_days, 30)
		self.assertEqual(doc.notice_served_days, 20)
		self.assertEqual(doc.notice_shortfall_days, 10)
		self.assertEqual(doc.workflow_state, "Draft")

	def test_full_notice_has_no_shortfall(self):
		doc = self.make_request()
		self.assertEqual(doc.notice_shortfall_days, 0)

	def test_probationer_gets_7_days(self):
		prob = make_employee("SepProb", make_user("sep.prob@example.com", ["Employee"]), employment_type="Probation")
		self.users["prob"] = "sep.prob@example.com"
		doc = self.make_request(employee=prob, user="prob", notice_days=60, last_working_date=str(add_days(self.today, 7)))
		self.assertEqual(doc.notice_days, 7)
		self.assertEqual(doc.notice_shortfall_days, 0)

	def test_contract_defaults_to_60(self):
		con = make_employee("SepCon", make_user("sep.con@example.com", ["Employee"]), employment_type="Contract")
		self.users["con"] = "sep.con@example.com"
		self.assertEqual(self.make_request(employee=con, user="con").notice_days, 60)

	def test_last_date_before_resignation(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_request(last_working_date=str(add_days(self.today, -1)))

	def test_employee_cannot_file_for_someone_else(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_request(employee=self.sup_emp, user="emp")

	def test_suspended_employee_blocked(self):
		frappe.db.set_value("Employee", self.emp, "status", "Suspended")
		with self.assertRaises(frappe.ValidationError):
			self.make_request()

	def test_under_investigation_blocked(self):
		frappe.db.set_value("Employee", self.emp, "custom_under_investigation", 1)
		with self.assertRaises(frappe.ValidationError):
			self.make_request()

	def test_obligation_flags(self):
		frappe.db.set_value("Employee", self.emp, "custom_training_study_undertaking", "STTP")
		doc = self.make_request()
		self.assertEqual(doc.has_training_study_undertaking, 1)
		self.assertEqual(doc.open_salary_advance, 0)


class TestWorkflow(SeparationBase):
	def test_supervisor_user_is_fetched(self):
		doc = self.make_request()
		self.assertEqual(doc.supervisor_user, self.users["sup"])
		self.assertEqual(doc.reports_to, self.sup_emp)

	def test_only_the_supervisor_can_approve(self):
		doc = self.make_request()
		self.act(doc, "Submit for Approval", "emp")
		for user in ("other", "emp"):
			with self.assertRaises((frappe.ValidationError, frappe.PermissionError)):
				self.act(doc, "Approve", user)
		self.assertEqual(self.act(doc, "Approve", "sup").workflow_state, "Pending CEO Approval")

	def test_only_ceo_can_approve_at_ceo_step(self):
		doc = self.make_request()
		self.act(doc, "Submit for Approval", "emp")
		self.act(doc, "Approve", "sup")
		with self.assertRaises(frappe.ValidationError):
			self.act(doc, "Approve", "sup")
		self.assertEqual(self.act(doc, "Approve", "ceo").workflow_state, "Approved by CEO")

	def test_supervisor_rejection_needs_reason(self):
		doc = self.make_request()
		self.act(doc, "Submit for Approval", "emp")
		with self.assertRaises(frappe.ValidationError):
			self.act(doc, "Reject", "sup")
		frappe.set_user(self.users["sup"])
		doc.reload()
		doc.decision_reason = "Handover not planned"
		doc.save()
		self.assertEqual(apply_workflow(doc, "Reject").workflow_state, "Rejected by Supervisor")

	def test_employee_can_amend_after_rejection(self):
		doc = self.make_request()
		self.act(doc, "Submit for Approval", "emp")
		frappe.set_user(self.users["sup"])
		doc.reload()
		doc.decision_reason = "Dates unclear"
		doc.save()
		apply_workflow(doc, "Reject")
		self.assertEqual(self.act(doc, "Amend and Resubmit", "emp").workflow_state, "Draft")
		self.assertEqual(self.act(doc, "Submit for Approval", "emp").workflow_state, "Pending Supervisor Approval")

	def test_ceo_withhold_needs_reason_and_closes(self):
		doc = self.make_request()
		self.act(doc, "Submit for Approval", "emp")
		self.act(doc, "Approve", "sup")
		with self.assertRaises(frappe.ValidationError):
			self.act(doc, "Withhold", "ceo")
		frappe.set_user(self.users["ceo"])
		doc.reload()
		doc.decision_reason = "Resignation to avoid disciplinary action"
		doc.save()
		self.assertEqual(apply_workflow(doc, "Withhold").workflow_state, "Withheld by CEO")
		with self.assertRaises(frappe.ValidationError):
			self.act(doc, "Amend and Resubmit", "emp")

	def test_withdraw_from_draft(self):
		doc = self.make_request()
		self.assertEqual(self.act(doc, "Withdraw", "emp").workflow_state, "Withdrawn")

	def test_other_employees_cannot_see_the_request(self):
		doc = self.make_request()
		frappe.set_user(self.users["other"])
		self.assertFalse(frappe.has_permission("Separation Request", "read", doc=doc))
		self.assertNotIn(doc.name, frappe.get_list("Separation Request", pluck="name"))
		frappe.set_user(self.users["sup"])
		self.assertTrue(frappe.has_permission("Separation Request", "read", doc=doc))

	def test_employee_cannot_edit_after_submission(self):
		doc = self.make_request()
		self.act(doc, "Submit for Approval", "emp")
		frappe.set_user(self.users["emp"])
		doc.reload()
		doc.reason_for_leaving = "changed"
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_ceo_approval_syncs_employee_and_locks_dates(self):
		doc = self.make_request()
		self.act(doc, "Submit for Approval", "emp")
		self.act(doc, "Approve", "sup")
		self.act(doc, "Approve", "ceo")
		values = frappe.db.get_value(
			"Employee", self.emp, ["resignation_letter_date", "relieving_date", "notice_number_of_days"], as_dict=True
		)
		self.assertEqual(str(values.resignation_letter_date), str(self.today))
		self.assertEqual(str(values.relieving_date), str(add_days(self.today, 30)))
		self.assertEqual(values.notice_number_of_days, 30)

		frappe.set_user(self.users["hr"])
		doc.reload()
		doc.last_working_date = str(add_days(self.today, 45))
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_hr_can_save_other_fields_after_approval_when_the_form_sends_text(self):
		"""The desk form posts dates and numbers as text; that must not look like a change to a locked field."""
		doc = self.make_request()
		self.act(doc, "Submit for Approval", "emp")
		self.act(doc, "Approve", "sup")
		self.act(doc, "Approve", "ceo")
		frappe.set_user(self.users["hr"])
		doc.reload()
		doc.resignation_date = str(doc.resignation_date)
		doc.last_working_date = str(doc.last_working_date)
		doc.notice_days = str(int(doc.notice_days))
		doc.nomination_reason = "Entered from the form after approval"
		doc.save()
		self.assertEqual(frappe.db.get_value("Separation Request", doc.name, "nomination_reason"), "Entered from the form after approval")


class TestEmployeeSeparation(SeparationBase):
	def test_acknowledge_creates_employee_separation_with_clearance(self):
		doc = self.make_request()
		doc = self.to_hr_acknowledged(doc)
		self.assertTrue(doc.employee_separation)
		es = frappe.get_doc("Employee Separation", doc.employee_separation)
		self.assertEqual(es.docstatus, 0)
		self.assertEqual(es.custom_separation_request, doc.name)
		self.assertEqual(es.custom_notice_days, 30)
		self.assertEqual(len(es.activities), 9)
		owners = {a.activity_name: (a.user, a.role) for a in es.activities}
		handover = next(v for k, v in owners.items() if k.startswith("Hand over charge"))
		self.assertEqual(handover[0], self.users["sup"])
		self.assertTrue(all(a.user or a.role for a in es.activities))

	def test_demise_has_single_offline_clearance(self):
		doc = self.make_request(separation_type="Demise")
		doc = self.to_hr_acknowledged(doc)
		es = frappe.get_doc("Employee Separation", doc.employee_separation)
		self.assertEqual([a.activity_name for a in es.activities], [DEMISE_ACTIVITY])

	def test_acknowledge_twice_creates_one_separation(self):
		doc = self.to_hr_acknowledged(self.make_request())
		first = doc.employee_separation
		doc.reload()
		doc.save()
		self.assertEqual(frappe.db.count("Employee Separation", {"custom_separation_request": doc.name}), 1)
		self.assertEqual(doc.employee_separation, first)


class TestClosure(SeparationBase):
	def acknowledged(self, last_working_date):
		doc = self.make_request(
			resignation_date=str(add_days(self.today, -40)), last_working_date=str(last_working_date), notice_days=30
		)
		return self.to_hr_acknowledged(doc)

	def test_closure_sets_left_disables_user_and_is_idempotent(self):
		doc = self.acknowledged(add_days(self.today, -1))
		frappe.set_user("Administrator")
		self.assertTrue(closure.close_separation(doc.name))
		emp = frappe.get_doc("Employee", self.emp)
		self.assertEqual(emp.status, "Left")
		self.assertEqual(str(emp.relieving_date), str(add_days(self.today, -1)))
		self.assertEqual(frappe.db.get_value("User", self.users["emp"], "enabled"), 0)
		self.assertFalse(closure.close_separation(doc.name))

	def test_scheduler_only_closes_due_requests(self):
		due = self.acknowledged(self.today)
		frappe.set_user("Administrator")
		other_sup = make_employee("SepSup2", make_user("sep.sup2@example.com", ["Employee"]))
		other = make_employee("SepEmp2", make_user("sep.emp2@example.com", ["Employee"]), reports_to=other_sup)
		self.users.update(emp2="sep.emp2@example.com")
		later = self.make_request(employee=other, user="emp2", last_working_date=str(add_days(self.today, 30)))
		self.act(later, "Submit for Approval", "emp2")
		frappe.set_user("Administrator")
		with mock.patch.object(frappe.db, "commit"):  # keep the test inside its rolled-back transaction
			closure.close_due_separations()
		self.assertEqual(frappe.db.get_value("Employee", self.emp, "status"), "Left")
		self.assertEqual(frappe.db.get_value("Employee", other, "status"), "Active")
		self.assertTrue(due.employee_separation)

	def test_leave_allocation_is_closed(self):
		doc = self.acknowledged(add_days(self.today, -1))
		last = str(add_days(self.today, -1))
		frappe.set_user("Administrator")
		lt = frappe.db.get_value("Leave Type", {"is_lwp": 0}, "name")
		if not lt:
			self.skipTest("no Leave Type on the site")
		alloc = frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": self.emp,
				"leave_type": lt,
				"from_date": str(add_days(self.today, -100)),
				"to_date": str(add_days(self.today, 200)),
				"new_leaves_allocated": 10,
			}
		).insert(ignore_permissions=True)
		alloc.submit()
		closure.close_separation(doc.name)
		self.assertEqual(str(frappe.db.get_value("Leave Allocation", alloc.name, "to_date")), last)


class TestClearanceAttachment(SeparationBase):
	def submitted_separation(self):
		doc = self.to_hr_acknowledged(self.make_request())
		frappe.set_user("Administrator")
		holiday_list = frappe.db.get_value("Holiday List", {"from_date": ["<=", self.today]}, ["name", "from_date"], as_dict=True)
		if not holiday_list:
			self.skipTest("no Holiday List covering today")
		hl = frappe.get_doc(
			{
				"doctype": "Holiday List Assignment",
				"applicable_for": "Employee",
				"assigned_to": self.emp,
				"holiday_list": holiday_list.name,
				"from_date": holiday_list.from_date,
			}
		).insert(ignore_permissions=True)
		hl.submit()
		es = frappe.get_doc("Employee Separation", doc.employee_separation)
		es.submit()
		es.reload()
		tasks = frappe.get_all(
			"Employee Boarding Activity", filters={"parent": es.name, "task": ["is", "set"]}, pluck="task"
		)
		return es, tasks

	def complete(self, task):
		t = frappe.get_doc("Task", task)
		t.status = "Completed"
		t.save(ignore_permissions=True)

	def test_last_task_needs_attachment(self):
		es, tasks = self.submitted_separation()
		self.assertEqual(len(tasks), 9)
		for task in tasks[:-1]:
			self.complete(task)  # earlier tasks are free to complete
		with self.assertRaises(frappe.ValidationError):
			self.complete(tasks[-1])

	def test_last_task_completes_with_attachment(self):
		es, tasks = self.submitted_separation()
		frappe.db.set_value("Employee Separation", es.name, "custom_clearance_attachment", "/files/signoff.pdf")
		for task in tasks:
			self.complete(task)
		self.assertEqual(frappe.db.count("Task", {"name": ["in", tasks], "status": "Completed"}), 9)


class TestNotifications(SeparationBase):
	def test_all_notifications_are_enabled_and_render(self):
		names = frappe.get_all(
			"Notification", filters={"document_type": "Separation Request"}, pluck="name"
		)
		self.assertGreaterEqual(len(names), 7)
		doc = self.make_request()
		for name in names:
			n = frappe.get_doc("Notification", name)
			self.assertTrue(n.enabled, name)
			self.assertTrue(n.recipients, name)
			context = {"doc": doc, "alert": n, "comments": None}
			self.assertTrue(frappe.render_template(n.subject, context).strip(), name)
			self.assertTrue(frappe.render_template(n.message, context).strip(), name)
			if n.condition:
				frappe.safe_eval(n.condition, None, {"doc": doc})
