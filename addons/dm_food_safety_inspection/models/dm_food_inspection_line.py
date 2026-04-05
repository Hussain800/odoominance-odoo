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

SEVERITY_FACTORS = {
    'low': 1.0,
    'medium': 2.0,
    'high': 3.0,
    'critical': 5.0,
}


def _severity_factor(severity):
    return SEVERITY_FACTORS.get(severity or 'medium', 2.0)


class FoodSafetyInspectionLine(models.Model):
    _name = 'dm.food.inspection.line'
    _description = 'Food Safety Inspection Line'
    _order = 'sequence, id'

    inspection_id = fields.Many2one('dm.food.inspection', required=True, ondelete='cascade', index=True)
    template_line_id = fields.Many2one('dm.food.checklist.template.line', ondelete='restrict', index=True)
    company_id = fields.Many2one(related='inspection_id.company_id', store=True, readonly=True, index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    check_type = fields.Selection(CHECK_TYPE_SELECTION, required=True, default='boolean')
    severity = fields.Selection(SEVERITY_SELECTION, required=True, default='medium')
    weight = fields.Float(default=1.0, required=True)
    expected_boolean = fields.Selection([('yes', 'Yes'), ('no', 'No')])
    expected_text = fields.Char()
    minimum_value = fields.Float()
    maximum_value = fields.Float()
    requires_evidence = fields.Boolean()
    note = fields.Html()
    actual_boolean = fields.Selection([('yes', 'Yes'), ('no', 'No')])
    actual_value = fields.Float()
    actual_text = fields.Char()
    evidence_note = fields.Html()
    result = fields.Selection(
        [('pending', 'Pending'), ('pass', 'Pass'), ('fail', 'Fail')],
        compute='_compute_result',
        store=True,
        readonly=False,
    )
    line_max_score = fields.Float(compute='_compute_result', store=True)
    line_score = fields.Float(compute='_compute_result', store=True)
    critical_failure = fields.Boolean(compute='_compute_result', store=True)

    _inspection_line_weight_positive = models.Constraint(
        'CHECK(weight > 0)',
        'Checklist line weight must be positive.',
    )

    @api.constrains('minimum_value', 'maximum_value')
    def _check_numeric_range(self):
        for line in self:
            if line.minimum_value and line.maximum_value and line.minimum_value > line.maximum_value:
                raise ValidationError(_('The minimum value cannot be greater than the maximum value.'))

    @api.constrains('result', 'requires_evidence', 'evidence_note')
    def _check_evidence_on_failed_lines(self):
        for line in self:
            if line.result == 'fail' and line.requires_evidence and not line.evidence_note:
                raise ValidationError(_('Failed lines that require evidence must include an evidence note.'))

    @api.depends(
        'check_type',
        'severity',
        'weight',
        'expected_boolean',
        'expected_text',
        'minimum_value',
        'maximum_value',
        'actual_boolean',
        'actual_value',
        'actual_text',
    )
    def _compute_result(self):
        for line in self:
            line_max_score = line.weight * _severity_factor(line.severity)
            if line.check_type == 'boolean':
                if line.actual_boolean not in ('yes', 'no'):
                    result = 'pending'
                else:
                    result = 'pass' if line.actual_boolean == line.expected_boolean else 'fail'
            elif line.check_type == 'numeric':
                if line.actual_value is False:
                    result = 'pending'
                else:
                    meets_minimum = line.minimum_value is False or line.actual_value >= line.minimum_value
                    meets_maximum = line.maximum_value is False or line.actual_value <= line.maximum_value
                    result = 'pass' if meets_minimum and meets_maximum else 'fail'
            else:
                actual_text = (line.actual_text or '').strip()
                expected_text = (line.expected_text or '').strip()
                if not actual_text:
                    result = 'pending'
                elif not expected_text:
                    result = 'pass'
                else:
                    result = 'pass' if expected_text.lower() in actual_text.lower() else 'fail'

            line.line_max_score = line_max_score
            line.line_score = line_max_score if result == 'pass' else 0.0
            line.result = result
            line.critical_failure = result == 'fail' and line.severity == 'critical'
