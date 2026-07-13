import {Component, onWillStart, useState} from "@odoo/owl";
import {ConfirmationDialog} from "@web/core/confirmation_dialog/confirmation_dialog";
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {sprintf} from "@web/core/utils/strings";
import {useService} from "@web/core/utils/hooks";

const MENU_WIDTH = 280;

export class ShiftGridAction extends Component {
    static template = "hr_shift_grid.ShiftGridAction";
    static props = {"*": true};

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.planningId =
            (this.props.action.params && this.props.action.params.planning_id) || false;
        // Ask for confirmation only once per opening of the grid.
        this.publishConfirmed = false;
        this.state = useState({data: null, menu: null});
        onWillStart(async () => {
            if (this.planningId) {
                this.state.data = await this.orm.call(
                    "hr.shift.planning",
                    "grid_data",
                    [[this.planningId]]
                );
            }
        });
    }

    // ------------------------------------------------------------------
    // Display helpers
    // ------------------------------------------------------------------

    isLocked(line) {
        return line.state === "holiday" || line.state === "on_leave";
    }

    cellLines(employee, day) {
        return employee.cells[day.day_number] || [];
    }

    hasEditableLine(lines) {
        return lines.some((line) => !this.isLocked(line));
    }

    freeLine(lines) {
        return lines.find((line) => !this.isLocked(line) && !line.template_id);
    }

    addIconClass(lines) {
        const classes = ["fa", "fa-plus", "o_hr_shift_grid_add"];
        if (lines.some((line) => line.template_id)) {
            classes.push("o_hr_shift_grid_add_more");
        }
        return classes.join(" ");
    }

    formatHours(hours) {
        return sprintf(_t("%(hours)s h"), {
            hours: Number.isInteger(hours) ? hours : hours.toFixed(1),
        });
    }

    gapLabel(count) {
        if (count === 1) {
            return _t("1 gap");
        }
        return sprintf(_t("%(count)s gaps"), {count});
    }

    cellClass(lines, day) {
        const classes = ["o_hr_shift_grid_cell"];
        if (day.is_today) {
            classes.push("o_hr_shift_grid_today");
        }
        if (!lines.length) {
            classes.push("o_hr_shift_grid_cell_off");
        } else if (!this.hasEditableLine(lines)) {
            classes.push("o_hr_shift_grid_cell_locked");
        } else if (!lines.some((line) => line.template_id)) {
            classes.push("o_hr_shift_grid_cell_empty");
        }
        return classes.join(" ");
    }

    // ------------------------------------------------------------------
    // Assignment menu
    // ------------------------------------------------------------------

    onRootClick() {
        this.state.menu = null;
    }

    openMenu(ev, employee, day, menu) {
        const rect = ev.currentTarget.getBoundingClientRect();
        this.state.menu = {
            employeeName: employee.name,
            dayLabel: `${day.label} ${day.date_label}`,
            x: Math.max(8, Math.min(rect.left, window.innerWidth - MENU_WIDTH - 8)),
            y: rect.bottom + 4,
            ...menu,
        };
    }

    onCellClick(ev, employee, day) {
        ev.stopPropagation();
        const lines = this.cellLines(employee, day);
        if (!this.hasEditableLine(lines)) {
            this.state.menu = null;
            return;
        }
        const free = this.freeLine(lines);
        if (free) {
            this.openMenu(ev, employee, day, {
                lineId: free.line_id,
                templateId: free.template_id,
            });
        } else {
            // Every line of the day is taken: offer to add a shift.
            this.openMenu(ev, employee, day, {
                add: true,
                employeeId: employee.employee_id,
                dayNumber: day.day_number,
                templateId: false,
            });
        }
    }

    onChipClick(ev, employee, day, line) {
        ev.stopPropagation();
        this.openMenu(ev, employee, day, {
            lineId: line.line_id,
            templateId: line.template_id,
        });
    }

    async pickTemplate(templateId) {
        const menu = this.state.menu;
        this.state.menu = null;
        if (!menu || templateId === menu.templateId) {
            return;
        }
        if (menu.add) {
            await this.mutate("grid_add", [
                [this.planningId],
                menu.employeeId,
                menu.dayNumber,
                templateId,
            ]);
            return;
        }
        await this.mutate("grid_write", [[this.planningId], menu.lineId, templateId]);
    }

    async removeShift() {
        const menu = this.state.menu;
        this.state.menu = null;
        if (!menu) {
            return;
        }
        await this.mutate("grid_write", [[this.planningId], menu.lineId, false]);
    }

    // ------------------------------------------------------------------
    // Native HTML5 drag & drop: move to an empty cell, swap with a
    // occupied one. Both are a single grid_swap() on the server.
    // ------------------------------------------------------------------

    onDragStart(ev, line) {
        ev.dataTransfer.setData("text/plain", String(line.line_id));
        ev.dataTransfer.effectAllowed = "move";
        ev.currentTarget.classList.add("o_hr_shift_grid_dragging");
    }

    onDragEnd(ev) {
        ev.currentTarget.classList.remove("o_hr_shift_grid_dragging");
    }

    onDragOver(ev, lines) {
        if (this.hasEditableLine(lines)) {
            ev.preventDefault();
            ev.dataTransfer.dropEffect = "move";
        }
    }

    onDragEnter(ev, lines) {
        if (this.hasEditableLine(lines)) {
            ev.currentTarget.classList.add("o_hr_shift_grid_drop");
        }
    }

    onDragLeave(ev) {
        if (!ev.currentTarget.contains(ev.relatedTarget)) {
            ev.currentTarget.classList.remove("o_hr_shift_grid_drop");
        }
    }

    async onDrop(ev, employee, day) {
        ev.preventDefault();
        ev.currentTarget.classList.remove("o_hr_shift_grid_drop");
        const sourceLineId = parseInt(ev.dataTransfer.getData("text/plain"), 10);
        const lines = this.cellLines(employee, day);
        // Dropping on a free line moves the shift there; on a full cell,
        // it swaps with the first shift of the day.
        const target =
            this.freeLine(lines) || lines.find((line) => !this.isLocked(line));
        if (!sourceLineId || !target || sourceLineId === target.line_id) {
            return;
        }
        await this.mutate("grid_swap", [
            [this.planningId],
            sourceLineId,
            target.line_id,
        ]);
    }

    // ------------------------------------------------------------------
    // Server round-trips
    // ------------------------------------------------------------------

    confirmPublished() {
        if (!this.state.data.published_on || this.publishConfirmed) {
            return Promise.resolve(true);
        }
        return new Promise((resolve) => {
            this.dialog.add(
                ConfirmationDialog,
                {
                    title: _t("Week already sent"),
                    body: _t(
                        "This week was already sent to the employees. " +
                            "The change will be logged in the chatter. Continue?"
                    ),
                    confirmLabel: _t("Continue"),
                    cancelLabel: _t("Cancel"),
                    confirm: () => {
                        this.publishConfirmed = true;
                        resolve(true);
                    },
                    cancel: () => resolve(false),
                },
                {onClose: () => resolve(false)}
            );
        });
    }

    async mutate(method, args) {
        if (!(await this.confirmPublished())) {
            return;
        }
        try {
            this.state.data = await this.orm.call("hr.shift.planning", method, args);
        } catch (error) {
            const message =
                (error.data && error.data.message) ||
                _t("The change could not be saved.");
            this.notification.add(message, {type: "danger"});
            this.state.data = await this.orm.call("hr.shift.planning", "grid_data", [
                [this.planningId],
            ]);
        }
    }
}

registry.category("actions").add("hr_shift_grid.action", ShiftGridAction);
