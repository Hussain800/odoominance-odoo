# -*- coding: utf-8 -*-

from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError, ValidationError


RISK_BAND_SELECTION = [
    ('low', 'Low'),
    ('medium', 'Medium'),
    ('high', 'High'),
    ('critical', 'Critical'),
]


class FoodSafetyInspection(models.Model):
    _name = 'dm.food.inspection'
    _description = 'Food Safety Inspection'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'inspection_date desc, id desc'
    _check_company_auto = True

    name = fields.Char(default='/', required=True, copy=False, tracking=True, index=True)
    inspection_date = fields.Datetime(default=fields.Datetime.now, required=True, tracking=True)
    due_date = fields.Date(tracking=True)
    template_id = fields.Many2one('dm.food.checklist.template', required=True, tracking=True, index=True)
    stage_id = fields.Many2one(
        'dm.food.inspection.stage',
        required=True,
        default=lambda self: self._default_stage(),
        tracking=True,
        index=True,
        group_expand='_read_group_stage_ids',
    )
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True, tracking=True, index=True)
    establishment_id = fields.Many2one('res.partner', required=True, tracking=True, index=True, domain="[('is_company', '=', True)]")
    inspector_id = fields.Many2one('res.users', default=lambda self: self.env.user, required=True, tracking=True, index=True)
    supervisor_id = fields.Many2one('res.users', tracking=True, index=True)
    line_ids = fields.One2many('dm.food.inspection.line', 'inspection_id', copy=True)
    note = fields.Html()
    follow_up_note = fields.Html()
    color = fields.Integer()
    risk_band = fields.Selection(RISK_BAND_SELECTION, compute='_compute_scores', store=True, tracking=True)
    risk_score = fields.Integer(compute='_compute_scores', store=True, tracking=True)
    compliance_score = fields.Integer(compute='_compute_scores', store=True, tracking=True)
    grade_id = fields.Many2one('dm.food.inspection.grade', compute='_compute_scores', store=True, tracking=True)
    line_count = fields.Integer(compute='_compute_scores', store=True)
    passed_line_count = fields.Integer(compute='_compute_scores', store=True)
    failed_line_count = fields.Integer(compute='_compute_scores', store=True)
    critical_fail_count = fields.Integer(compute='_compute_scores', store=True)
    pending_line_count = fields.Integer(compute='_compute_scores', store=True)
    total_possible_score = fields.Float(compute='_compute_scores', store=True)
    achieved_score = fields.Float(compute='_compute_scores', store=True)
    is_overdue = fields.Boolean(compute='_compute_scores', store=True)
    done = fields.Boolean(related='stage_id.done', store=True)

    _risk_score_range = models.Constraint(
        'CHECK(risk_score >= 0 AND risk_score <= 100)',
        'Risk score must stay between 0 and 100.',
    )

    _compliance_score_range = models.Constraint(
        'CHECK(compliance_score >= 0 AND compliance_score <= 100)',
        'Compliance score must stay between 0 and 100.',
    )

    @api.model
    def _default_stage(self):
        stage = self.env['dm.food.inspection.stage'].search([('code', '=', 'draft')], limit=1)
        if not stage:
            stage = self.env['dm.food.inspection.stage'].search([], limit=1)
        return stage.id

    @api.model
    def _get_stage(self, code):
        stage = self.env['dm.food.inspection.stage'].search([('code', '=', code)], limit=1)
        if not stage:
            raise UserError(_('Missing inspection stage: %s') % code)
        return stage

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        search_domain = self.env['ir.rule']._compute_domain(stages._name)
        stage_ids = stages.sudo()._search(search_domain, order=stages._order)
        return stages.browse(stage_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('dm.food.inspection') or '/'
            template_id = vals.get('template_id')
            if template_id and not vals.get('line_ids'):
                template = self.env['dm.food.checklist.template'].browse(template_id)
                vals['line_ids'] = [Command.create(line._to_inspection_line_vals()) for line in template.line_ids]
        return super().create(vals_list)

    def write(self, vals):
        if 'stage_id' in vals and not self.env.context.get('dm_food_safety_allow_stage_write'):
            raise UserError(_('Use the workflow actions to change the inspection stage.'))
        return super().write(vals)

    @api.onchange('template_id')
    def _onchange_template_id(self):
        if not self.template_id:
            self.line_ids = [Command.clear()]
            return
        self.line_ids = [Command.clear()] + [
            Command.create(line._to_inspection_line_vals())
            for line in self.template_id.line_ids
        ]

    @api.depends(
        'line_ids.line_score',
        'line_ids.line_max_score',
        'line_ids.result',
        'line_ids.critical_failure',
        'due_date',
        'stage_id',
        'company_id',
    )
    def _compute_scores(self):
        grade_model = self.env['dm.food.inspection.grade']
        for inspection in self:
            lines = inspection.line_ids
            total_possible_score = sum(lines.mapped('line_max_score'))
            achieved_score = sum(lines.mapped('line_score'))
            line_count = len(lines)
            passed_line_count = len(lines.filtered(lambda line: line.result == 'pass'))
            failed_line_count = len(lines.filtered(lambda line: line.result == 'fail'))
            critical_fail_count = len(lines.filtered(lambda line: line.critical_failure))
            pending_line_count = len(lines.filtered(lambda line: line.result == 'pending'))
            compliance_score = round((achieved_score / total_possible_score) * 100) if total_possible_score else 100
            compliance_score = max(0, min(100, compliance_score))
            risk_score = 100 - compliance_score
            if risk_score >= 60:
                risk_band = 'critical'
            elif risk_score >= 30:
                risk_band = 'high'
            elif risk_score >= 10:
                risk_band = 'medium'
            else:
                risk_band = 'low'

            grade = grade_model.search(
                [
                    ('active', '=', True),
                    '|', ('company_id', '=', False), ('company_id', '=', inspection.company_id.id),
                    ('min_compliance', '<=', compliance_score),
                    ('max_compliance', '>=', compliance_score),
                ],
                order='sequence, min_compliance desc, id',
                limit=1,
            )
            if not grade:
                grade = grade_model.search(
                    [
                        ('active', '=', True),
                        '|', ('company_id', '=', False), ('company_id', '=', inspection.company_id.id),
                    ],
                    order='sequence, min_compliance desc, id',
                    limit=1,
                )

            inspection.total_possible_score = total_possible_score
            inspection.achieved_score = achieved_score
            inspection.compliance_score = compliance_score
            inspection.risk_score = risk_score
            inspection.risk_band = risk_band
            inspection.grade_id = grade
            inspection.line_count = line_count
            inspection.passed_line_count = passed_line_count
            inspection.failed_line_count = failed_line_count
            inspection.critical_fail_count = critical_fail_count
            inspection.pending_line_count = pending_line_count
            inspection.is_overdue = bool(inspection.due_date and not inspection.stage_id.done and inspection.due_date < fields.Date.context_today(inspection))

    @api.constrains('stage_id', 'line_ids', 'line_ids.result', 'line_ids.evidence_note')
    def _check_terminal_integrity(self):
        for inspection in self:
            if inspection.stage_id.code in {'passed', 'failed'} and inspection.pending_line_count:
                raise ValidationError(_('Completed inspections must have all checklist lines evaluated.'))
            if inspection.stage_id.code == 'passed' and (inspection.critical_fail_count or inspection.compliance_score < 60):
                raise ValidationError(_('An inspection can only be marked as passed when the compliance score is at least 60 and no critical check failed.'))
            for line in inspection.line_ids.filtered(lambda inspection_line: inspection_line.result == 'fail' and inspection_line.requires_evidence):
                if not line.evidence_note:
                    raise ValidationError(_('Failed lines that require evidence must include an evidence note.'))

    def _set_stage(self, stage_code, message):
        stage = self._get_stage(stage_code)
        self.with_context(dm_food_safety_allow_stage_write=True).write({'stage_id': stage.id})
        if message:
            self.message_post(body=message)

    def action_prepare(self):
        for inspection in self:
            if inspection.stage_id.code != 'draft':
                raise UserError(_('Only draft inspections can be prepared.'))
            if not inspection.line_ids:
                raise UserError(_('Select a checklist template with at least one line before preparing the inspection.'))
            inspection._set_stage('ready', _('Inspection prepared and ready to start.'))

    def action_start(self):
        for inspection in self:
            if inspection.stage_id.code != 'ready':
                raise UserError(_('Only ready inspections can be started.'))
            inspection._set_stage('in_progress', _('Inspection started.'))

    def action_submit_for_review(self):
        for inspection in self:
            if inspection.stage_id.code != 'in_progress':
                raise UserError(_('Only in-progress inspections can be submitted for review.'))
            if inspection.pending_line_count:
                raise UserError(_('All checklist lines must be answered before submitting the inspection.'))
            missing_evidence = inspection.line_ids.filtered(lambda line: line.result == 'fail' and line.requires_evidence and not line.evidence_note)
            if missing_evidence:
                raise UserError(_('Failed lines that require evidence must include an evidence note before submission.'))
            inspection._set_stage('waiting_supervisor', _('Inspection submitted for supervisor review.'))

    def action_mark_passed(self):
        for inspection in self:
            if inspection.stage_id.code != 'waiting_supervisor':
                raise UserError(_('Only inspections waiting for supervisor review can be marked as passed.'))
            if inspection.critical_fail_count or inspection.compliance_score < 60:
                raise UserError(_('This inspection does not meet the minimum compliance needed to pass.'))
            inspection.supervisor_id = self.env.user
            inspection._set_stage('passed', _('Inspection passed by supervisor.'))

    def action_mark_failed(self):
        for inspection in self:
            if inspection.stage_id.code != 'waiting_supervisor':
                raise UserError(_('Only inspections waiting for supervisor review can be marked as failed.'))
            inspection.supervisor_id = self.env.user
            inspection._set_stage('failed', _('Inspection failed by supervisor.'))

    def action_cancel(self):
        for inspection in self:
            if inspection.stage_id.code == 'cancelled':
                continue
            inspection._set_stage('cancelled', _('Inspection cancelled.'))

    def action_reset_draft(self):
        for inspection in self:
            inspection._set_stage('draft', _('Inspection reset to draft.'))
