# -*- coding: utf-8 -*-

from odoo import fields, models


class FoodViolationTag(models.Model):
    _name = 'dm.food.violation.tag'
    _description = 'Food Violation Tag'
    _order = 'name'
    _check_company_auto = True

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    color = fields.Integer(default=0)
    active = fields.Boolean(default=True)
    description = fields.Text()
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    finding_ids = fields.Many2many(
        'dm.food.finding',
        'dm_food_finding_violation_tag_rel',
        'tag_id',
        'finding_id',
        string='Findings',
    )

    _code_unique = models.Constraint(
        'unique(code, company_id)',
        'The violation tag code must be unique per company.',
    )
