# -*- coding: utf-8 -*-

from odoo import fields, models


FOOD_RISK_SELECTION = [
    ('low', 'Low'),
    ('medium', 'Medium'),
    ('high', 'High'),
    ('critical', 'Critical'),
]


class ResPartner(models.Model):
    _inherit = 'res.partner'

    food_trade_license_no = fields.Char(string='Food Trade License No.', copy=False)
    food_owner_name = fields.Char(string='Food Owner Name', copy=False)
    food_cuisine_type = fields.Char(string='Food Cuisine Type', copy=False)
    food_risk_level = fields.Selection(FOOD_RISK_SELECTION, string='Food Risk Level', default='medium', copy=False)
    food_inspection_count = fields.Integer(compute='_compute_food_safety_counts')
    food_finding_count = fields.Integer(compute='_compute_food_safety_counts')
    food_certificate_count = fields.Integer(compute='_compute_food_safety_counts')

    def _compute_food_safety_counts(self):
        inspection_model = self.env['dm.food.inspection'].sudo()
        finding_model = self.env['dm.food.finding'].sudo()
        certificate_model = self.env['dm.food.certificate'].sudo()
        for partner in self:
            partner.food_inspection_count = inspection_model.search_count([('establishment_id', '=', partner.id)])
            partner.food_finding_count = finding_model.search_count([('establishment_id', '=', partner.id)])
            partner.food_certificate_count = certificate_model.search_count([('establishment_id', '=', partner.id)])

    def action_view_food_safety_inspections(self):
        self.ensure_one()
        action = self.env.ref('dm_food_safety_inspection.action_dm_food_inspection').read()[0]
        action['domain'] = [('establishment_id', '=', self.id)]
        action['context'] = {}
        return action

    def action_view_food_safety_findings(self):
        self.ensure_one()
        action = self.env.ref('dm_food_safety_inspection.action_dm_food_finding').read()[0]
        action['domain'] = [('establishment_id', '=', self.id)]
        action['context'] = {}
        return action

    def action_view_food_safety_certificates(self):
        self.ensure_one()
        action = self.env.ref('dm_food_safety_inspection.action_dm_food_certificate').read()[0]
        action['domain'] = [('establishment_id', '=', self.id)]
        action['context'] = {}
        return action
