const HR_ROLES = ["System Manager", "HR Manager", "HR User"];

frappe.ui.form.on("Separation Request", {
	setup(frm) {
		// an employee files for themselves only; HR can pick anyone
		frm.set_query("employee", () =>
			HR_ROLES.some((role) => frappe.user.has_role(role)) ? {} : { filters: { user_id: frappe.session.user } }
		);
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.employee) {
			frappe.db
				.get_value("Employee", { user_id: frappe.session.user, status: "Active" }, "name")
				.then((r) => {
					if (r.message && r.message.name) frm.set_value("employee", r.message.name);
				});
		}
	},

	refresh(frm) {
		frm.trigger("show_flags");
		frm.trigger("full_and_final_button");
	},

	full_and_final_button(frm) {
		const is_hr = HR_ROLES.some((role) => frappe.user.has_role(role));
		if (!is_hr || frm.doc.workflow_state !== "HR Acknowledged") return;
		if (frm.doc.full_and_final_statement) {
			frm.add_custom_button(__("Full and Final Statement"), () =>
				frappe.set_route("Form", "Full and Final Statement", frm.doc.full_and_final_statement)
			);
			return;
		}
		frm.add_custom_button(__("Prepare Full and Final Statement"), () => {
			frappe.call({
				method: "gdl_custom_app.gdl_hr.fnf.start_full_and_final",
				args: { request: frm.doc.name },
				freeze: true,
				callback: (r) => r.message && frappe.set_route("Form", "Full and Final Statement", r.message),
			});
		});
	},

	show_flags(frm) {
		const notes = [];
		const flags = [];
		if (frm.doc.open_salary_advance) flags.push(__("outstanding salary advance"));
		if (frm.doc.open_travel_advance) flags.push(__("outstanding travel advance"));
		if (frm.doc.has_training_study_undertaking) flags.push(__("training / study leave undertaking"));
		if (frm.doc.is_suspended_or_under_investigation) flags.push(__("suspension / investigation"));
		if (flags.length) notes.push(__("Open obligations: {0}", [flags.join(", ")]));
		if (frm.doc.notice_shortfall_days > 0) {
			notes.push(
				__("Notice shortfall of {0} day(s): pay in lieu is recovered in the Full and Final Statement.", [
					frm.doc.notice_shortfall_days,
				])
			);
		}
		if (frm.doc.nomination_status && frm.doc.nomination_status !== "Valid") {
			notes.push(__("Nomination: {0}.", [frm.doc.nomination_status]));
		}
		frm.dashboard.clear_headline();
		if (notes.length) frm.dashboard.set_headline_alert(notes.join("<br>"), "orange");
	},

	employee(frm) {
		if (!frm.doc.employee) return;
		frappe.db.get_value("Employee", frm.doc.employee, "notice_number_of_days").then((r) => {
			if (!frm.doc.notice_days && r.message) {
				frm.set_value("notice_days", r.message.notice_number_of_days || 30);
			}
		});
	},

	resignation_date: calc_notice,
	last_working_date: calc_notice,
	notice_days: calc_notice,
});

function calc_notice(frm) {
	const { resignation_date, last_working_date, notice_days } = frm.doc;
	if (!resignation_date || !last_working_date) return;
	const served = frappe.datetime.get_diff(last_working_date, resignation_date);
	frm.set_value("notice_served_days", served);
	frm.set_value("notice_shortfall_days", Math.max(0, (notice_days || 0) - served));
}
