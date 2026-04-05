# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


CHECK_TYPE_SELECTION = [
    ('boolean', 'Yes / No'),
    ('numeric', 'Numeric'),
    ('text', 'Text'),
]

SEVERITY_SELECTION = [
    ('low', 'Low'),
    ('medium', 'Medium'),
    ('high', 'High'),
    ('critical', 'Critical'),
]


class FoodSafetyChecklistTemplate(models.Model):
    _name = 'dm.food.checklist.template'
    _description = 'Food Safety Checklist Template'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name, id'

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    note = fields.Html()
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, index=True)
    line_ids = fields.One2many('dm.food.checklist.template.line', 'template_id', copy=True)
    line_count = fields.Integer(compute='_compute_line_count')

    _template_code_uniq = models.Constraint(
        'UNIQUE(code)',
        'Template code must be unique.',
    )

    @api.depends('line_ids')
    def _compute_line_count(self):
        for template in self:
            template.line_count = len(template.line_ids)


class FoodSafetyChecklistTemplateLine(models.Model):
    _name = 'dm.food.checklist.template.line'
    _description = 'Food Safety Checklist Template Line'
    _order = 'sequence, id'

    template_id = fields.Many2one('dm.food.checklist.template', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='template_id.company_id', store=True, readonly=True, index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, translate=True)
    check_type = fields.Selection(CHECK_TYPE_SELECTION, required=True, default='boolean')
    severity = fields.Selection(SEVERITY_SELECTION, required=True, default='medium')
    weight = fields.Float(default=1.0, required=True)
    expected_boolean = fields.Selection([('yes', 'Yes'), ('no', 'No')])
    expected_text = fields.Char()
    minimum_value = fields.Float()
    maximum_value = fields.Float()
    requires_evidence = fields.Boolean()
    note = fields.Html()
    active = fields.Boolean(default=True)

    _template_line_weight_positive = models.Constraint(
        'CHECK(weight > 0)',
        'Template line weight must be positive.',
    )

    @api.constrains('check_type', 'expected_boolean', 'expected_text', 'minimum_value', 'maximum_value')
    def _check_value_configuration(self):
        for line in self:
            if line.check_type == 'numeric' and line.minimum_value is False and line.maximum_value is False:
                raise ValidationError(_('Numeric checklist lines need a minimum or maximum value.'))
            if line.check_type == 'text' and not line.expected_text:
                raise ValidationError(_('Text checklist lines need an expected text value.'))
            if line.check_type == 'boolean' and line.expected_boolean not in ('yes', 'no'):
                raise ValidationError(_('Boolean checklist lines need an expected yes/no value.'))
            if line.minimum_value and line.maximum_value and line.minimum_value > line.maximum_value:
                raise ValidationError(_('The minimum value cannot be greater than the maximum value.'))

    def _to_inspection_line_vals(self):
        self.ensure_one()
        return {
            'template_line_id': self.id,
            'sequence': self.sequence,
            'name': self.name,
            'check_type': self.check_type,
            'severity': self.severity,
            'weight': self.weight,
            'expected_boolean': self.expected_boolean,
            'expected_text': self.expected_text,
            'minimum_value': self.minimum_value,
            'maximum_value': self.maximum_value,
            'requires_evidence': self.requires_evidence,
            'note': self.note,
        }
