# -*- coding: utf-8 -*-

from odoo import api, fields, models


class FoodSafetyInspectionStage(models.Model):
    _name = 'dm.food.inspection.stage'
    _description = 'Food Safety Inspection Stage'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean()
    done = fields.Boolean()
    requires_supervisor = fields.Boolean()
    color = fields.Integer()
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=False, index=True)

    _inspection_stage_code_uniq = models.Constraint(
        'UNIQUE(code)',
        'Stage code must be unique.',
    )

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        search_domain = self.env['ir.rule']._compute_domain(stages._name)
        stage_ids = stages.sudo()._search(search_domain, order=stages._order)
        return stages.browse(stage_ids)
