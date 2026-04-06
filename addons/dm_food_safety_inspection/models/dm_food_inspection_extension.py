# -*- coding: utf-8 -*-

from odoo import api, fields, models


class FoodSafetyInspection(models.Model):
    _inherit = 'dm.food.inspection'

    finding_ids = fields.One2many('dm.food.finding', 'inspection_id', string='Findings')
    certificate_ids = fields.One2many('dm.food.certificate', 'inspection_id', string='Certificates')
    finding_count = fields.Integer(compute='_compute_related_counts', store=True)
    certificate_count = fields.Integer(compute='_compute_related_counts', store=True)
    critical_finding_count = fields.Integer(compute='_compute_related_counts', store=True)

    @api.depends('finding_ids.severity', 'certificate_ids')
    def _compute_related_counts(self):
        for record in self:
            record.finding_count = len(record.finding_ids)
            record.certificate_count = len(record.certificate_ids)
            record.critical_finding_count = len(record.finding_ids.filtered(lambda finding: finding.severity == 'critical'))

    def action_view_findings(self):
        self.ensure_one()
        action = self.env.ref('dm_food_safety_inspection.action_dm_food_finding').read()[0]
        action['domain'] = [('inspection_id', '=', self.id)]
        action['context'] = {
            'default_inspection_id': self.id,
            'default_establishment_id': self.establishment_id.id,
        }
        return action

    def action_view_certificates(self):
        self.ensure_one()
        action = self.env.ref('dm_food_safety_inspection.action_dm_food_certificate').read()[0]
        action['domain'] = [('inspection_id', '=', self.id)]
        action['context'] = {
            'default_inspection_id': self.id,
            'default_establishment_id': self.establishment_id.id,
        }
        return action
