# -*- coding: utf-8 -*-

from odoo import api, fields, models


FINDING_SEVERITY_SELECTION = [
    ('low', 'Low'),
    ('medium', 'Medium'),
    ('high', 'High'),
    ('critical', 'Critical'),
]


FINDING_STATUS_SELECTION = [
    ('open', 'Open'),
    ('in_progress', 'In Progress'),
    ('resolved', 'Resolved'),
    ('waived', 'Waived'),
]


class FoodSafetyFinding(models.Model):
    _name = 'dm.food.finding'
    _description = 'Food Safety Finding'
    _order = 'severity desc, deadline_date, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True

    name = fields.Char(required=True, copy=False, default='/', tracking=True, index=True)
    inspection_id = fields.Many2one('dm.food.inspection', required=True, ondelete='cascade', tracking=True, index=True, check_company=True)
    establishment_id = fields.Many2one('res.partner', related='inspection_id.establishment_id', store=True, readonly=True, index=True)
    company_id = fields.Many2one('res.company', related='inspection_id.company_id', store=True, readonly=True, index=True)
    inspector_id = fields.Many2one('res.users', related='inspection_id.inspector_id', store=True, readonly=True, index=True)
    severity = fields.Selection(FINDING_SEVERITY_SELECTION, default='medium', required=True, tracking=True)
    status = fields.Selection(FINDING_STATUS_SELECTION, default='open', required=True, tracking=True)
    deadline_date = fields.Date(tracking=True)
    is_overdue = fields.Boolean(compute='_compute_is_overdue', store=True)
    critical = fields.Boolean(compute='_compute_critical', store=True)
    description = fields.Text()
    corrective_action = fields.Text()
    tag_ids = fields.Many2many(
        'dm.food.violation.tag',
        'dm_food_finding_violation_tag_rel',
        'finding_id',
        'tag_id',
        string='Violation Tags',
    )

    _name_unique = models.Constraint(
        'unique(name, company_id)',
        'The finding reference must be unique per company.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('dm.food.finding') or '/'
        return super().create(vals_list)

    @api.depends('deadline_date', 'status')
    def _compute_is_overdue(self):
        for record in self:
            today = fields.Date.context_today(record)
            record.is_overdue = bool(
                record.deadline_date
                and record.status in {'open', 'in_progress'}
                and record.deadline_date < today
            )

    @api.depends('severity')
    def _compute_critical(self):
        for record in self:
            record.critical = record.severity == 'critical'

    def action_mark_in_progress(self):
        self.write({'status': 'in_progress'})

    def action_mark_resolved(self):
        self.write({'status': 'resolved'})

    def action_mark_waived(self):
        self.write({'status': 'waived'})

    def action_reopen(self):
        self.write({'status': 'open'})
