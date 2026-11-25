// Exit Interview (GDL): HR opens the employee's confidential questionnaire from the interview.
frappe.ui.form.on("Exit Interview", {
	refresh(frm) {
		if (frm.doc.custom_separation_request) {
			// the GDL questionnaire replaces HRMS's emailed web form for interviews from this process
			frm.remove_custom_button(__("Send Exit Questionnaire"));
			setTimeout(() => frm.remove_custom_button(__("Send Exit Questionnaire")), 100);
		}
		if (frm.doc.custom_response) {
			frm.add_custom_button(__("View Questionnaire Answers"), () =>
				frappe.set_route("Form", "Exit Interview Response", frm.doc.custom_response)
			);
		}
	},
});
