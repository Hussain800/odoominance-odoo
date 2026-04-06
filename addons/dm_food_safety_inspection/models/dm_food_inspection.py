# -*- coding: utf-8 -*-

import json
import logging
import os
from urllib import error as urllib_error
from urllib import request as urllib_request

from markupsafe import escape
from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError, ValidationError


_logger = logging.getLogger(__name__)


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
    ai_summary_json = fields.Json(copy=False)
    ai_summary_html = fields.Html(copy=False)
    ai_summary_source = fields.Selection(
        [('fallback', 'Fallback'), ('ai', 'AI')],
        copy=False,
        readonly=True,
        tracking=True,
    )
    ai_summary_generated_at = fields.Datetime(copy=False, readonly=True, tracking=True)
    ai_summary_applied_at = fields.Datetime(copy=False, readonly=True, tracking=True)
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
            inspection.supervisor_id = self._get_review_supervisor_user()
            inspection._set_stage('passed', _('Inspection passed by supervisor.'))

    def action_mark_failed(self):
        for inspection in self:
            if inspection.stage_id.code != 'waiting_supervisor':
                raise UserError(_('Only inspections waiting for supervisor review can be marked as failed.'))
            inspection.supervisor_id = self._get_review_supervisor_user()
            inspection._set_stage('failed', _('Inspection failed by supervisor.'))

    def action_cancel(self):
        for inspection in self:
            if inspection.stage_id.code == 'cancelled':
                continue
            inspection._set_stage('cancelled', _('Inspection cancelled.'))

    def action_reset_draft(self):
        for inspection in self:
            inspection._set_stage('draft', _('Inspection reset to draft.'))

    def _dashboard_quick_actions(self):
        actions = [
            {
                'key': 'open_inspections',
                'label': _('All inspections'),
                'description': _('Open the complete inspection board.'),
                'abbr': 'INS',
                'tone': 'teal',
            },
            {
                'key': 'new_inspection',
                'label': _('New inspection'),
                'description': _('Create a fresh inspection from a checklist template.'),
                'abbr': 'NEW',
                'tone': 'gold',
            },
            {
                'key': 'review_queue',
                'label': _('Review queue'),
                'description': _('Focus on inspections waiting for supervisor approval.'),
                'abbr': 'REV',
                'tone': 'rose',
            },
        ]
        if self.env.user.has_group('dm_food_safety_inspection.group_food_safety_supervisor'):
            actions.append(
                {
                    'key': 'templates',
                    'label': _('Checklist templates'),
                    'description': _('Maintain the template library and scoring standards.'),
                    'abbr': 'TMP',
                    'tone': 'slate',
                }
            )
        return actions

    def _get_review_supervisor_user(self):
        supervisor = self.env.user
        if supervisor._is_superuser():
            supervisor = self.env.ref('base.user_admin')
        return supervisor

    @api.model
    def get_dashboard_payload(self):
        inspection_model = self.env['dm.food.inspection']
        stage_model = self.env['dm.food.inspection.stage']
        inspections = inspection_model.search([])

        total_count = len(inspections)
        active_count = inspection_model.search_count([('stage_id.done', '=', False)])
        awaiting_review_count = inspection_model.search_count([('stage_id.code', '=', 'waiting_supervisor')])
        overdue_count = inspection_model.search_count([('is_overdue', '=', True)])
        critical_count = sum(1 for inspection in inspections if inspection.risk_band == 'critical' or inspection.stage_id.code == 'failed')
        passed_count = inspection_model.search_count([('stage_id.code', '=', 'passed')])
        failed_count = inspection_model.search_count([('stage_id.code', '=', 'failed')])
        evaluation_count = passed_count + failed_count
        average_group = inspection_model.read_group([], ['compliance_score:avg'], [])
        average_data = average_group[0] if average_group else {}
        average_compliance = round(average_data.get('compliance_score_avg') or average_data.get('compliance_score') or 0)
        pass_rate = round((passed_count / evaluation_count) * 100) if evaluation_count else 0

        risk_labels = dict(RISK_BAND_SELECTION)
        dashboard_payload = {
            'headline': _('Food safety command center'),
            'subheadline': _(
                '%(active)s active inspections, %(review)s awaiting review, %(critical)s critical risk'
            ) % {
                'active': active_count,
                'review': awaiting_review_count,
                'critical': critical_count,
            },
            'hero_badges': [
                {'label': _('Active queue'), 'value': active_count},
                {'label': _('Awaiting review'), 'value': awaiting_review_count},
                {'label': _('Critical risk'), 'value': critical_count},
            ],
            'kpis': [
                {
                    'key': 'total_inspections',
                    'label': _('Live inspections'),
                    'value': total_count,
                    'help': _('All records visible to your account.'),
                    'tone': 'teal',
                },
                {
                    'key': 'awaiting_review',
                    'label': _('Awaiting review'),
                    'value': awaiting_review_count,
                    'help': _('Waiting for supervisor approval.'),
                    'tone': 'amber',
                },
                {
                    'key': 'overdue_inspections',
                    'label': _('Overdue'),
                    'value': overdue_count,
                    'help': _('Past due and still open.'),
                    'tone': 'rose',
                },
                {
                    'key': 'critical_risk',
                    'label': _('Critical risk'),
                    'value': critical_count,
                    'help': _('High urgency records that need attention.'),
                    'tone': 'slate',
                },
                {
                    'key': 'average_compliance',
                    'label': _('Average compliance'),
                    'value': average_compliance,
                    'suffix': '%',
                    'help': _('Average across visible inspections.'),
                    'tone': 'gold',
                },
                {
                    'key': 'pass_rate',
                    'label': _('Pass rate'),
                    'value': pass_rate,
                    'suffix': '%',
                    'help': _('Completed inspections that passed.'),
                    'tone': 'emerald',
                },
            ],
            'risk_distribution': [],
            'stage_distribution': [],
            'recent_inspections': [],
            'quick_actions': self._dashboard_quick_actions(),
        }

        for risk_code, risk_label in RISK_BAND_SELECTION:
            count = inspection_model.search_count([('risk_band', '=', risk_code)])
            dashboard_payload['risk_distribution'].append(
                {
                    'key': risk_code,
                    'label': risk_label,
                    'count': count,
                    'count_text': _('%(count)s inspections') % {'count': count},
                    'percentage': round((count / total_count) * 100) if total_count else 0,
                    'tone': risk_code,
                }
            )

        for stage in stage_model.search([], order='sequence, id'):
            count = inspection_model.search_count([('stage_id', '=', stage.id)])
            dashboard_payload['stage_distribution'].append(
                {
                    'key': stage.code,
                    'label': stage.name,
                    'count': count,
                    'count_text': _('%(count)s inspections') % {'count': count},
                    'percentage': round((count / total_count) * 100) if total_count else 0,
                    'tone': stage.code,
                }
            )

        recent_records = inspection_model.search([], order='inspection_date desc, id desc', limit=5)
        for inspection in recent_records:
            dashboard_payload['recent_inspections'].append(
                {
                    'id': inspection.id,
                    'name': inspection.name,
                    'establishment': inspection.establishment_id.display_name,
                    'stage': inspection.stage_id.display_name,
                    'risk_band': risk_labels.get(inspection.risk_band, inspection.risk_band or ''),
                    'risk_score': inspection.risk_score,
                    'compliance_score': inspection.compliance_score,
                    'compliance_text': '%s%%' % inspection.compliance_score,
                    'grade': inspection.grade_id.display_name if inspection.grade_id else '',
                    'inspection_date': inspection.inspection_date.strftime('%b %d, %Y %H:%M') if inspection.inspection_date else '',
                    'is_overdue': inspection.is_overdue,
                }
            )

        return dashboard_payload

    @api.model
    def action_dashboard_get_action(self, action_key):
        if action_key == 'open_inspections':
            action = self.env.ref('dm_food_safety_inspection.action_dm_food_inspection').read()[0]
            action['name'] = _('All inspections')
            action['context'] = {}
            return action
        if action_key == 'review_queue':
            action = self.env.ref('dm_food_safety_inspection.action_dm_food_inspection').read()[0]
            action['name'] = _('Review queue')
            action['context'] = {}
            action['domain'] = [('stage_id.code', '=', 'waiting_supervisor')]
            return action
        if action_key == 'new_inspection':
            return {
                'type': 'ir.actions.act_window',
                'name': _('New inspection'),
                'res_model': 'dm.food.inspection',
                'view_mode': 'form',
                'views': [(False, 'form')],
                'target': 'current',
                'context': {
                    'default_inspector_id': self.env.user.id,
                    'default_company_id': self.env.company.id,
                },
            }
        if action_key == 'templates':
            if not self.env.user.has_group('dm_food_safety_inspection.group_food_safety_supervisor'):
                raise UserError(_('Only supervisors can manage checklist templates.'))
            action = self.env.ref('dm_food_safety_inspection.action_dm_food_template').read()[0]
            action['context'] = {}
            return action
        raise UserError(_('Unknown dashboard action: %s') % action_key)

    def _build_ai_summary_context(self):
        self.ensure_one()
        top_findings = []
        recommendation_items = []

        if self.critical_fail_count:
            top_findings.append(
                _('%(count)s critical checklist item(s) failed.') % {'count': self.critical_fail_count}
            )
            recommendation_items.append(
                _('Resolve every critical finding before the inspection is escalated.'))
        if self.pending_line_count:
            top_findings.append(
                _('%(count)s checklist item(s) are still pending.') % {'count': self.pending_line_count}
            )
            recommendation_items.append(
                _('Complete the remaining checklist items and add any missing evidence.'))
        if self.is_overdue:
            top_findings.append(_('The inspection is overdue.'))
            recommendation_items.append(_('Escalate the inspection and close out the open findings today.'))
        if self.risk_score >= 60:
            top_findings.append(_('Overall risk is critical.'))
            recommendation_items.append(_('Prioritise the highest-risk corrective actions immediately.'))
        elif self.risk_score >= 30:
            top_findings.append(_('Overall risk is high.'))
            recommendation_items.append(_('Review the failed controls and verify corrective actions.'))
        elif self.risk_score >= 10:
            top_findings.append(_('Overall risk is moderate.'))
            recommendation_items.append(_('Monitor the weaker controls and confirm follow-up evidence.'))
        else:
            top_findings.append(_('The inspection is currently low risk.'))
            recommendation_items.append(_('Keep the current controls in place and file the record.'))

        if not recommendation_items:
            recommendation_items.append(_('Continue with the existing workflow and supervisor review.'))

        return {
            'inspection_name': self.name,
            'establishment_name': self.establishment_id.display_name,
            'inspection_date': self.inspection_date.strftime('%b %d, %Y %H:%M') if self.inspection_date else '',
            'due_date': self.due_date.strftime('%b %d, %Y') if self.due_date else '',
            'stage_name': self.stage_id.display_name,
            'stage_code': self.stage_id.code,
            'risk_band': self.risk_band,
            'risk_score': self.risk_score,
            'compliance_score': self.compliance_score,
            'grade': self.grade_id.display_name if self.grade_id else '',
            'critical_fail_count': self.critical_fail_count,
            'pending_line_count': self.pending_line_count,
            'top_findings': top_findings,
            'recommended_actions': recommendation_items,
            'line_items': [
                {
                    'name': line.name,
                    'result': line.result,
                    'severity': line.severity,
                    'critical_failure': line.critical_failure,
                    'score': line.line_score,
                    'max_score': line.line_max_score,
                    'evidence_note': line.evidence_note or '',
                }
                for line in self.line_ids
            ],
        }

    def _build_fallback_ai_summary(self):
        self.ensure_one()
        context = self._build_ai_summary_context()
        summary_bits = [
            _('%(establishment)s is at %(risk_band)s risk with a compliance score of %(score)s%%.')
            % {
                'establishment': context['establishment_name'],
                'risk_band': context['risk_band'] or _('unknown'),
                'score': context['compliance_score'],
            }
        ]
        if context['critical_fail_count']:
            summary_bits.append(
                _('%(count)s critical item(s) still need attention.') % {'count': context['critical_fail_count']}
            )
        if context['pending_line_count']:
            summary_bits.append(
                _('%(count)s checklist item(s) remain open.') % {'count': context['pending_line_count']}
            )
        if self.is_overdue:
            summary_bits.append(_('The record is overdue and should be resolved today.'))

        return {
            'title': _('Advisory summary for %(name)s') % {'name': self.name},
            'summary': ' '.join(summary_bits),
            'priority': 'critical' if self.risk_score >= 60 else 'high' if self.risk_score >= 30 else 'medium' if self.risk_score >= 10 else 'low',
            'top_findings': context['top_findings'],
            'recommended_actions': context['recommended_actions'],
            'source': 'fallback',
        }

    def _request_openai_summary(self):
        self.ensure_one()
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            return None

        model = os.environ.get('OPENAI_MODEL', 'gpt-5.4-mini')
        context = self._build_ai_summary_context()
        prompt = _(
            'Return one JSON object with the keys title, summary, priority, top_findings, and recommended_actions. '
            'Keep it advisory only, do not change the workflow stage, and speak clearly for a food safety supervisor. '
            'Use short bullet-style strings inside the arrays.'
        )
        payload = {
            'model': model,
            'messages': [
                {'role': 'system', 'content': prompt + ' JSON only.'},
                {'role': 'user', 'content': json.dumps(context, ensure_ascii=False)},
            ],
            'response_format': {'type': 'json_object'},
            'temperature': 0.2,
        }
        request = urllib_request.Request(
            'https://api.openai.com/v1/chat/completions',
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            method='POST',
        )

        try:
            with urllib_request.urlopen(request, timeout=20) as response:
                body = json.loads(response.read().decode('utf-8'))
        except (urllib_error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
            _logger.exception('Food safety AI summary provider failed; using fallback summary.')
            return None

        choices = body.get('choices') or []
        if not choices:
            return None
        message = choices[0].get('message') or {}
        content = message.get('content') or ''
        if not content:
            return None

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return None
        return self._sanitize_ai_summary_payload(data)

    def _sanitize_ai_summary_payload(self, data):
        self.ensure_one()
        title = data.get('title') or _('Advisory summary for %(name)s') % {'name': self.name}
        summary = data.get('summary') or self._build_fallback_ai_summary()['summary']
        priority = data.get('priority') if data.get('priority') in {'low', 'medium', 'high', 'critical'} else 'medium'
        top_findings = data.get('top_findings') or []
        recommended_actions = data.get('recommended_actions') or []
        return {
            'title': title,
            'summary': summary,
            'priority': priority,
            'top_findings': [str(item) for item in top_findings][:5],
            'recommended_actions': [str(item) for item in recommended_actions][:5],
            'source': 'ai',
        }

    def _render_ai_summary_html(self, payload):
        summary_items = ''.join('<li>%s</li>' % escape(item) for item in payload['top_findings'])
        action_items = ''.join('<li>%s</li>' % escape(item) for item in payload['recommended_actions'])
        return (
            '<div class="o_dm_ai_summary_note">'
            '<section class="o_dm_ai_summary_shell">'
            '<header class="o_dm_ai_summary_header">'
            '<section class="o_dm_ai_summary_title_block">'
            '<p class="o_dm_ai_summary_kicker">AI summary</p>'
            '<h3>%s</h3>'
            '</section>'
            '<span class="o_dm_ai_summary_priority o_dm_priority_%s">%s</span>'
            '</header>'
            '<p class="o_dm_ai_summary_body">%s</p>'
            '<section class="o_dm_ai_summary_columns">'
            '<article>'
            '<h4>%s</h4>'
            '<ul>%s</ul>'
            '</article>'
            '<article>'
            '<h4>%s</h4>'
            '<ul>%s</ul>'
            '</article>'
            '</section>'
            '</section>'
            '</div>'
        ) % (
            escape(payload['title']),
            escape(payload['priority']),
            escape(payload['priority'].title()),
            escape(payload['summary']),
            escape(_('Top findings')),
            summary_items,
            escape(_('Recommended actions')),
            action_items,
        )

    def _merge_ai_summary_into_follow_up(self, existing_note, summary_html):
        marker = '<div class="o_dm_ai_summary_note">'
        existing_note = existing_note or ''
        start = existing_note.find(marker)
        if start == -1:
            if existing_note:
                return '%s<hr/>%s' % (existing_note, summary_html)
            return summary_html

        end = existing_note.find('</div>', start)
        if end == -1:
            if existing_note:
                return '%s<hr/>%s' % (existing_note, summary_html)
            return summary_html

        end += len('</div>')
        return '%s%s%s' % (existing_note[:start], summary_html, existing_note[end:])

    def _generate_ai_summary_payload(self):
        self.ensure_one()
        payload = self._request_openai_summary()
        if payload:
            return payload
        return self._build_fallback_ai_summary()

    def action_generate_ai_summary(self):
        for inspection in self:
            payload = inspection._generate_ai_summary_payload()
            inspection.write(
                {
                    'ai_summary_json': payload,
                    'ai_summary_html': inspection._render_ai_summary_html(payload),
                    'ai_summary_source': payload['source'],
                    'ai_summary_generated_at': fields.Datetime.now(),
                }
            )
            inspection.message_post(
                body=_('AI summary generated for %(name)s using %(source)s mode.') % {
                    'name': inspection.name,
                    'source': payload['source'],
                }
            )

    def action_apply_ai_summary(self):
        for inspection in self:
            if not inspection.ai_summary_html:
                raise UserError(_('Generate an AI summary before applying it to the follow-up note.'))
            follow_up_note = inspection._merge_ai_summary_into_follow_up(inspection.follow_up_note, inspection.ai_summary_html)
            inspection.write(
                {
                    'follow_up_note': follow_up_note,
                    'ai_summary_applied_at': fields.Datetime.now(),
                }
            )
            inspection.message_post(body=_('AI summary applied to the follow-up note.'))
