frappe.ui.form.on("Separation Request", {
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
				__("Notice shortfall of {0} day(s): pay in lieu is deducted manually by HR.", [
					frm.doc.notice_shortfall_days,
				])
			);
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
