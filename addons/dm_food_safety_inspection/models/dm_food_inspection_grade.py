# -*- coding: utf-8 -*-

from odoo import fields, models


class FoodSafetyInspectionGrade(models.Model):
    _name = 'dm.food.inspection.grade'
    _description = 'Food Safety Inspection Grade'
    _order = 'sequence, min_compliance desc, id'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    min_compliance = fields.Float(required=True)
    max_compliance = fields.Float(required=True)
    color = fields.Integer()
    description = fields.Text()
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=False, index=True)

    _inspection_grade_code_uniq = models.Constraint(
        'UNIQUE(code)',
        'Grade code must be unique.',
    )

    _inspection_grade_range = models.Constraint(
        'CHECK(min_compliance >= 0 AND max_compliance <= 100 AND min_compliance <= max_compliance)',
        'Grade range must stay within 0..100 and the minimum must be lower than the maximum.',
    )
