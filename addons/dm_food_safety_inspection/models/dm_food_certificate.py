# -*- coding: utf-8 -*-

from odoo import api, fields, models


CERTIFICATE_STATUS_SELECTION = [
    ('draft', 'Draft'),
    ('active', 'Active'),
    ('expired', 'Expired'),
    ('revoked', 'Revoked'),
]


class FoodSafetyCertificate(models.Model):
    _name = 'dm.food.certificate'
    _description = 'Food Safety Certificate'
    _order = 'issue_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True

    name = fields.Char(string='Certificate No.', required=True, copy=False, default='/', tracking=True, index=True)
    inspection_id = fields.Many2one('dm.food.inspection', required=True, ondelete='cascade', tracking=True, index=True, check_company=True)
    establishment_id = fields.Many2one('res.partner', related='inspection_id.establishment_id', store=True, readonly=True, index=True)
    company_id = fields.Many2one('res.company', related='inspection_id.company_id', store=True, readonly=True, index=True)
    inspector_id = fields.Many2one('res.users', related='inspection_id.inspector_id', store=True, readonly=True, index=True)
    issue_date = fields.Date(default=fields.Date.context_today, required=True, tracking=True)
    expiry_date = fields.Date(required=True, tracking=True)
    status = fields.Selection(CERTIFICATE_STATUS_SELECTION, default='draft', required=True, tracking=True)
    notes = fields.Text()
    is_expired = fields.Boolean(compute='_compute_is_expired', store=True)

    _name_unique = models.Constraint(
        'unique(name, company_id)',
        'The certificate number must be unique per company.',
    )

    _date_range_valid = models.Constraint(
        'CHECK(expiry_date >= issue_date)',
        'The certificate expiry date must be on or after the issue date.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('dm.food.certificate') or '/'
        return super().create(vals_list)

    @api.depends('expiry_date', 'status')
    def _compute_is_expired(self):
        for record in self:
            today = fields.Date.context_today(record)
            record.is_expired = bool(
                record.expiry_date
                and record.status in {'draft', 'active'}
                and record.expiry_date < today
            )

    def action_mark_active(self):
        self.write({'status': 'active'})

    def action_mark_revoked(self):
        self.write({'status': 'revoked'})

    def action_mark_expired(self):
        self.write({'status': 'expired'})

    def action_reset_draft(self):
        self.write({'status': 'draft'})
