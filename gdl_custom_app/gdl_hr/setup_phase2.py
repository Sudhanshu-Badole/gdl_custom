"""Idempotent setup for Phase 2: the Annexure 1 exit questionnaire template, Exit Interview and Employee
Separation custom fields, the Employee Nomination workflow and notifications. Run from the
hr_exit_nomination_setup patch."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from gdl_custom_app.gdl_hr.exit_interview import SERVICE_BANDS, LONGEST_BAND, SERVICE_QUESTION, TEMPLATE_NAME, TYPE_QUESTION

NOMINATION = "Employee Nomination"
NOMINATION_WORKFLOW = "Employee Nomination Approval"

CUSTOM_FIELDS = {
	"Exit Interview": [
		{"fieldname": "custom_method", "label": "Method", "fieldtype": "Select", "options": "\nIn-person\nVirtual", "insert_after": "date"},
		{"fieldname": "custom_service_band", "label": "Years of Service", "fieldtype": "Data", "read_only": 1, "insert_after": "date_of_joining"},
		{"fieldname": "custom_process_section", "label": "Separation Process", "fieldtype": "Section Break", "insert_after": "interview_summary"},
		{"fieldname": "custom_separation_request", "label": "Separation Request", "fieldtype": "Link", "options": "Separation Request", "read_only": 1, "no_copy": 1, "insert_after": "custom_process_section"},
		{"fieldname": "custom_separation_type", "label": "Separation Type", "fieldtype": "Link", "options": "Separation Type", "read_only": 1, "insert_after": "custom_separation_request"},
		{"fieldname": "custom_process_column", "fieldtype": "Column Break", "insert_after": "custom_separation_type"},
		{"fieldname": "custom_personal_email", "label": "Personal Email ID", "fieldtype": "Data", "options": "Email", "read_only": 1, "insert_after": "custom_process_column"},
		{"fieldname": "custom_response", "label": "Questionnaire Response", "fieldtype": "Link", "options": "Exit Interview Response", "read_only": 1, "no_copy": 1, "insert_after": "custom_personal_email"},
		{"fieldname": "custom_waive_reason", "label": "Response Waived Reason", "fieldtype": "Small Text", "insert_after": "custom_response", "description": "Only when the employee will not submit the questionnaire. HR can then complete the interview without it."},
	],
	"Employee Separation": [
		{"fieldname": "custom_exit_interview", "label": "Exit Interview", "fieldtype": "Link", "options": "Exit Interview", "read_only": 1, "no_copy": 1, "insert_after": "custom_separation_type"},
		{"fieldname": "custom_nomination_status", "label": "Nomination Status", "fieldtype": "Data", "read_only": 1, "insert_after": "custom_exit_interview"},
	],
}

# ---- Annexure 1: Exit Interview Form --------------------------------------------------------

RATING_4 = "Rating 4"
RATING_5 = "Rating 5"
RATING_4_OPTIONS = ["Strongly Disagree", "Disagree", "Agree", "Strongly Agree"]
RATING_5_OPTIONS = ["1 - Strongly Disagree", "2 - Disagree", "3 - Neutral", "4 - Agree", "5 - Strongly Agree"]


def q(question, answer_type="Text", options=None, mandatory=0):
	return {"question": question, "answer_type": answer_type, "options": options, "mandatory": mandatory}


def ratings(statements, answer_type=RATING_4):
	return [q(s, answer_type) for s in statements]


PARTS = (
	(
		"Part I: Employee Details",
		[
			q(
				SERVICE_QUESTION,
				"Single Choice",
				[band for _limit, band in SERVICE_BANDS] + [LONGEST_BAND],
				1,
			),
			q(TYPE_QUESTION, "Single Choice", ["Voluntary Resignation", "Superannuation", "Early Retirement"]),
		],
	),
	(
		"Part II: Reasons for Leaving",
		[
			q(
				"Please indicate the reasons that apply to your situation",
				"Multi Select",
				[
					"Higher pay/ Better benefits",
					"Career advancement/job growth",
					"Conflict with supervisor",
					"Health reasons",
					"Management issues",
					"Company culture",
					"Work life balance",
					"Job Satisfaction",
					"Further Education",
					"Family/Personal reasons",
					"Job security",
					"Work flexibility",
				],
			),
			q("Please elaborate why you chose the above reasons"),
		],
	),
	(
		"Part III: Job Satisfaction",
		ratings(
			[
				"Opportunities for career advancement",
				"Workload was manageable",
				"Sufficient resources and staff were available",
				"Your colleagues listened and appreciated your suggestions",
				"Your skills were effectively used",
				"You had access to adequate training and development programs",
				"You received proper job description (responsibilities) and clear directions to do the work",
				"The annual performance targets were set in line with your job responsibilities and departmental business objectives",
				"Fair evaluation of work results",
				"Appreciating the results of your work",
				"You fully understood how your individual work performance impacts the overall corporate business target achievement",
			]
		)
		+ [
			q("What do you think can be improved about the job?"),
			q(
				"What types of career opportunities are important to you?",
				"Multi Select",
				["Promotional Opportunities", "Position Rotations", "Increased Responsibilities", "Special Projects", "Others"],
			),
			q("If you selected Others, please elaborate"),
			q("Pertaining to your role in the company, what could we have done differently to make you stay?"),
			q("Can you describe your level of job satisfaction?", "Single Choice", ["Excellent", "Above Average", "Fair", "Poor"]),
			q("If rated Fair or Poor, please outline what the perceived problems were"),
		],
	),
	(
		"Part IV: Management",
		ratings(
			[
				"Gave fair and equal treatment",
				"Was available to discuss job related issues",
				"Encouraged feedback and suggestions",
				"Maintained consistent policies and practices",
				"Provided recognition for achievements",
				"Gave opportunities for learning and development",
				"Provided constructive feedback",
				"Clearly communicated decisions and how they would affect your work",
			]
		)
		+ [q("What are your suggestions or improvements to Management?")],
	),
	(
		"Part V: Remuneration & Benefits",
		ratings(
			[
				"The salary was adequate in relation to responsibilities",
				"Wages were paid on time",
				"Other benefits were good",
				"Work-life balance was promoted and practiced",
				"The company's post-retirement benefits were attractive",
			]
		)
		+ [q("What improvements, other benefits could the company offer?")],
	),
	(
		"Part VI: The Company",
		ratings(
			[
				"The induction program was conducted timely and was helpful",
				"The work environment was positive and conducive",
				"Had adequate equipment to do the work",
				"Got on well with other staff within the company",
				"There were sufficient staff to cover the work",
				"The company was efficient in its dealings with both internal and external customers",
				"Internal communication worked well",
				"There was no bullying or harassment",
				"Supports employee welfare",
				"The business did not discriminate against any employee",
				"Environments that support cooperation",
				"Treat employees who quit their jobs with respect",
			]
		)
		+ [q("What do you think can be improved about the Department and Company?")],
	),
	(
		"Part VII: Supervisor",
		ratings(
			[
				"Provided constructive feedback",
				"Recognized accomplishments",
				"Clearly communicated expectations",
				"Treated you fairly and respectfully",
				"Coached, trained, & developed you",
				"Acknowledged employees' contributions",
				"Encouraged teamwork & cooperation",
				"Resolved concerns promptly",
				"Encouraged/Listened to suggestions & feedback",
				"Kept employees informed",
				"Supported work-life balance",
				"Provided appropriate & challenging assignments",
				"Followed policies and practices",
			],
			RATING_5,
		)
		+ [
			q(
				"What actions has your supervisor taken to encourage you to stay on your team?",
				"Multi Select",
				[
					"Individual Conversation",
					"Proposal to extend/Change the scope of task",
					"Promotion proposal",
					"Change in salary",
					"There were no actions",
				],
				1,
			),
			q("What are your suggestions or improvements to your supervisor?"),
			q("How long ago did you make the decision to leave?", "Single Choice", ["1-3 months", "4-6 months", "7-12 months", "Over a year"], 1),
			q(
				"How likely is it that you will recommend us as an employer to your friends or family?",
				"Single Choice",
				["Yes, without reservations.", "Yes, with reservations.", "No"],
				1,
			),
			q("What could we change to make you rate us better?", mandatory=1),
			q("Is there anything else you would like to discuss as you depart the organization that has not been addressed?"),
			q("If you were speaking to the founders/owners instead of me, what advice would you give them?"),
			q("What advice would you give us on how to improve the Exit Interview process?"),
		],
	),
)

# ---- Employee Nomination workflow -----------------------------------------------------------

OWNER = "doc.owner == frappe.session.user or doc.employee_user == frappe.session.user"

# (state, allow_edit role, style)
NOMINATION_STATES = (
	("Draft", "Employee", "Warning"),
	("Draft", "HR Manager", "Warning"),
	("Submitted", "HR Manager", "Primary"),
	("Verified", "HR Manager", "Success"),
)

# (state, action, next state, role, condition)
NOMINATION_TRANSITIONS = (
	("Draft", "Submit Nomination", "Submitted", "Employee", OWNER),
	("Draft", "Submit Nomination", "Submitted", "HR Manager", None),
	("Submitted", "Verify", "Verified", "HR Manager", None),
	("Submitted", "Return to Draft", "Draft", "HR Manager", None),
	("Verified", "Return to Draft", "Draft", "HR Manager", None),
)

NOMINATION_LINK = '<p><a href="{{ frappe.utils.get_url_to_form(doc.doctype, doc.name) }}">{{ doc.name }}</a></p>'

# (name, doctype, event, condition, subject, intro, document-field recipients, role recipients)
NOTIFICATIONS = (
	(
		"Employee Nomination - Submitted",
		NOMINATION,
		"Value Change",
		'doc.workflow_state == "Submitted"',
		"Nomination from {{ doc.employee_name }} awaits verification",
		"An employee submitted their nomination. Please check the nominees, the shares and the signed form.",
		[],
		["HR Manager"],
	),
	(
		"Employee Nomination - Verified",
		NOMINATION,
		"Value Change",
		'doc.workflow_state == "Verified"',
		"Your nomination has been verified",
		"HR verified your nomination. No further action is needed.",
		["employee_user"],
		[],
	),
	(
		"Employee Nomination - Returned",
		NOMINATION,
		"Value Change",
		'doc.workflow_state == "Draft" and doc.remarks',
		"Your nomination was returned for correction",
		"HR returned your nomination. See the Remarks, correct it and submit it again.<br>{{ doc.remarks }}",
		["employee_user"],
		[],
	),
	(
		"Exit Interview Response - Submitted",
		"Exit Interview Response",
		"Submit",
		None,
		"Exit questionnaire received from {{ doc.employee_name }}",
		"The employee submitted the exit questionnaire. The answers are confidential to HR.",
		[],
		["HR Manager"],
	),
)


def execute():
	frappe.db.commit()  # custom fields reload meta; the doctypes must exist first
	create_custom_fields(CUSTOM_FIELDS, update=True)
	create_template()
	create_nomination_workflow()
	create_notifications()
	frappe.clear_cache()


def create_template():
	if frappe.db.exists("Exit Interview Template", TEMPLATE_NAME):
		doc = frappe.get_doc("Exit Interview Template", TEMPLATE_NAME)
		doc.set("questions", [])
	else:
		doc = frappe.new_doc("Exit Interview Template")
		doc.template_name = TEMPLATE_NAME
	doc.is_active = 1
	for part, questions in PARTS:
		for item in questions:
			options = item["options"]
			if item["answer_type"] == RATING_4:
				options = RATING_4_OPTIONS
			elif item["answer_type"] == RATING_5:
				options = RATING_5_OPTIONS
			doc.append(
				"questions",
				{
					"part": part,
					"question": item["question"],
					"answer_type": item["answer_type"],
					"options": "\n".join(options) if options else None,
					"mandatory": item["mandatory"],
				},
			)
	doc.save(ignore_permissions=True)


def create_nomination_workflow():
	for state, _role, style in NOMINATION_STATES:
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": state, "style": style}).insert(
				ignore_permissions=True
			)
	for action in {t[1] for t in NOMINATION_TRANSITIONS}:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert(
				ignore_permissions=True
			)

	if frappe.db.exists("Workflow", NOMINATION_WORKFLOW):
		wf = frappe.get_doc("Workflow", NOMINATION_WORKFLOW)
		wf.set("states", [])
		wf.set("transitions", [])
	else:
		wf = frappe.new_doc("Workflow")
		wf.workflow_name = NOMINATION_WORKFLOW
	wf.document_type = NOMINATION
	wf.workflow_state_field = "workflow_state"
	wf.is_active = 1
	wf.send_email_alert = 0
	for state, role, _style in NOMINATION_STATES:
		wf.append("states", {"state": state, "doc_status": "0", "allow_edit": role})
	for state, action, next_state, role, condition in NOMINATION_TRANSITIONS:
		wf.append(
			"transitions",
			{
				"state": state,
				"action": action,
				"next_state": next_state,
				"allowed": role,
				"condition": condition,
				"allow_self_approval": 1,
			},
		)
	wf.save(ignore_permissions=True)


def create_notifications():
	for name, doctype, event, condition, subject, intro, fields, roles in NOTIFICATIONS:
		doc = frappe.get_doc("Notification", name) if frappe.db.exists("Notification", name) else frappe.new_doc("Notification")
		doc.name = name
		doc.update(
			{
				"subject": subject,
				"document_type": doctype,
				"event": event,
				"value_changed": "workflow_state" if event == "Value Change" else None,
				"condition": condition,
				"channel": "Email",
				"enabled": 1,
				"message": f"<p>{intro}</p>{NOMINATION_LINK}",
			}
		)
		doc.set("recipients", [])
		for field in fields:
			doc.append("recipients", {"receiver_by_document_field": field})
		for role in roles:
			doc.append("recipients", {"receiver_by_role": role})
		doc.save(ignore_permissions=True)
