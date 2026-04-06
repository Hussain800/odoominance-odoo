# -*- coding: utf-8 -*-

import json
import os
from datetime import timedelta
from unittest.mock import patch
from urllib import request as urllib_request

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFoodSafetyInspection(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Inspection = self.env['dm.food.inspection']
        self.template = self.env.ref('dm_food_safety_inspection.dm_food_safety_template_restaurant')
        self.partner = self.env['res.partner'].create({
            'name': 'Palm Harbor Grill',
            'is_company': True,
            'city': 'Dubai',
            'country_id': self.env.ref('base.ae').id,
        })
        self.partner_2 = self.env['res.partner'].create({
            'name': 'Desert Dunes Kitchen',
            'is_company': True,
            'city': 'Dubai',
            'country_id': self.env.ref('base.ae').id,
        })
        self.pass_stage = self.env.ref('dm_food_safety_inspection.dm_food_safety_stage_passed')
        self.fail_stage = self.env.ref('dm_food_safety_inspection.dm_food_safety_stage_failed')
        self.ready_stage = self.env.ref('dm_food_safety_inspection.dm_food_safety_stage_ready')

    def _create_inspection(self, partner=None):
        return self.Inspection.create({
            'template_id': self.template.id,
            'establishment_id': (partner or self.partner).id,
            'inspector_id': self.env.ref('base.user_admin').id,
        })

    def _set_all_pass_values(self, inspection):
        lines = {line.template_line_id.sequence: line for line in inspection.line_ids}
        lines[10].write({
            'actual_boolean': 'yes',
            'requires_evidence': True,
            'evidence_note': 'Soap, water, and disposable towels were available.',
        })
        lines[20].write({
            'actual_value': 4.0,
            'requires_evidence': True,
            'evidence_note': 'Chiller logs were within range.',
        })
        lines[30].write({'actual_boolean': 'yes'})
        lines[40].write({'actual_boolean': 'yes'})
        lines[50].write({
            'actual_boolean': 'yes',
            'requires_evidence': True,
            'evidence_note': 'Current pest control certificate attached.',
        })
        lines[60].write({'actual_text': 'Staff briefing recorded in the inspection log.'})

    def _set_failure_values(self, inspection):
        lines = {line.template_line_id.sequence: line for line in inspection.line_ids}
        lines[10].write({
            'actual_boolean': 'no',
            'requires_evidence': True,
            'evidence_note': 'Soap dispenser was empty and no disposable towels were available.',
        })
        lines[20].write({
            'actual_value': 8.5,
            'requires_evidence': True,
            'evidence_note': 'The cold room thermometer read 8.5C at the time of inspection.',
        })
        lines[30].write({'actual_boolean': 'yes'})
        lines[40].write({'actual_boolean': 'yes'})
        lines[50].write({
            'actual_boolean': 'no',
            'requires_evidence': True,
            'evidence_note': 'No current pest control certificate was presented.',
        })
        lines[60].write({'actual_text': 'No staff briefing recorded.'})

    def test_template_lines_are_copied_and_passed_inspection_computes_scores(self):
        inspection = self._create_inspection()

        self.assertEqual(len(inspection.line_ids), len(self.template.line_ids))
        self._set_all_pass_values(inspection)

        inspection.action_prepare()
        inspection.action_start()
        inspection.action_submit_for_review()
        inspection.action_mark_passed()

        self.assertEqual(inspection.stage_id, self.pass_stage)
        self.assertEqual(inspection.compliance_score, 100)
        self.assertEqual(inspection.risk_band, 'low')
        self.assertEqual(inspection.grade_id.code, 'A')
        self.assertEqual(inspection.pending_line_count, 0)
        self.assertEqual(inspection.supervisor_id, self.env.ref('base.user_admin'))

    def test_direct_stage_write_is_blocked(self):
        inspection = self._create_inspection(self.partner_2)

        with self.assertRaises(UserError):
            inspection.write({'stage_id': self.ready_stage.id})

    def test_failed_inspection_cannot_be_marked_passed(self):
        inspection = self._create_inspection(self.partner_2)
        self._set_failure_values(inspection)

        inspection.action_prepare()
        inspection.action_start()
        inspection.action_submit_for_review()

        with self.assertRaises(UserError):
            inspection.action_mark_passed()

        inspection.action_mark_failed()

        self.assertEqual(inspection.stage_id, self.fail_stage)
        self.assertLess(inspection.compliance_score, 60)
        self.assertEqual(inspection.grade_id.code, 'F')

    def test_dashboard_payload_reports_live_kpis(self):
        baseline_payload = self.Inspection.get_dashboard_payload()
        baseline_kpis = {item['key']: item for item in baseline_payload['kpis']}

        passed_inspection = self._create_inspection(self.partner)
        self._set_all_pass_values(passed_inspection)
        passed_inspection.action_prepare()
        passed_inspection.action_start()
        passed_inspection.action_submit_for_review()
        passed_inspection.with_user(self.env.ref('base.user_admin')).action_mark_passed()

        failed_inspection = self._create_inspection(self.partner_2)
        self._set_failure_values(failed_inspection)
        failed_inspection.action_prepare()
        failed_inspection.action_start()
        failed_inspection.action_submit_for_review()
        failed_inspection.action_mark_failed()

        overdue_inspection = self._create_inspection()
        overdue_inspection.write({'due_date': fields.Date.to_date(fields.Date.context_today(self.env.user)) - timedelta(days=2)})

        payload = self.Inspection.get_dashboard_payload()
        kpis = {item['key']: item for item in payload['kpis']}
        quick_actions = {item['key'] for item in payload['quick_actions']}

        self.assertEqual(
            kpis['total_inspections']['value'],
            baseline_kpis['total_inspections']['value'] + 3,
        )
        self.assertEqual(
            kpis['overdue_inspections']['value'],
            baseline_kpis['overdue_inspections']['value'] + 1,
        )
        self.assertGreaterEqual(
            kpis['critical_risk']['value'],
            baseline_kpis['critical_risk']['value'] + 1,
        )
        self.assertGreaterEqual(kpis['pass_rate']['value'], 0)
        self.assertLessEqual(kpis['pass_rate']['value'], 100)
        self.assertIn('open_inspections', quick_actions)
        self.assertIn('new_inspection', quick_actions)
        self.assertIn('review_queue', quick_actions)
        self.assertIn('templates', quick_actions)

    def test_ai_summary_generation_and_apply_flow(self):
        inspection = self._create_inspection(self.partner_2)
        self._set_failure_values(inspection)
        inspection.action_prepare()
        inspection.action_start()
        inspection.action_submit_for_review()

        with patch.object(type(inspection), '_request_groq_summary', return_value=None):
            inspection.action_generate_ai_summary()

        self.assertEqual(inspection.ai_summary_source, 'fallback')
        self.assertTrue(inspection.ai_summary_html)
        self.assertTrue(inspection.ai_summary_json)
        self.assertIn('summary', inspection.ai_summary_json)

        inspection.action_apply_ai_summary()

        self.assertIn('o_dm_ai_summary_note', inspection.follow_up_note)
        self.assertIsNotNone(inspection.ai_summary_applied_at)

        note_before = inspection.follow_up_note
        inspection.action_apply_ai_summary()

        self.assertEqual(note_before, inspection.follow_up_note)
        self.assertEqual(inspection.follow_up_note.count('o_dm_ai_summary_note'), 1)

    def test_ai_summary_generation_uses_groq_provider(self):
        inspection = self._create_inspection(self.partner_2)
        self._set_failure_values(inspection)
        inspection.action_prepare()
        inspection.action_start()
        inspection.action_submit_for_review()

        groq_response = {
            'choices': [
                {
                    'message': {
                        'content': json.dumps(
                            {
                                'title': 'Groq summary',
                                'summary': 'Groq generated summary.',
                                'priority': 'high',
                                'top_findings': ['Finding one'],
                                'recommended_actions': ['Action one'],
                            }
                        )
                    }
                }
            ]
        }
        captured_request = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(groq_response).encode('utf-8')

        def fake_urlopen(request, timeout=20):
            captured_request['url'] = request.get_full_url()
            captured_request['authorization'] = request.get_header('Authorization')
            captured_request['model'] = json.loads(request.data.decode('utf-8'))['model']
            return FakeResponse()

        with patch.dict(os.environ, {'GROQ_API_KEY': 'test-groq-key', 'GROQ_MODEL': 'llama-3.1-70b-versatile'}, clear=False):
            with patch.object(urllib_request, 'urlopen', side_effect=fake_urlopen):
                inspection.action_generate_ai_summary()

        self.assertEqual(captured_request['url'], 'https://api.groq.com/openai/v1/chat/completions')
        self.assertEqual(captured_request['authorization'], 'Bearer test-groq-key')
        self.assertEqual(captured_request['model'], 'llama-3.1-70b-versatile')
        self.assertEqual(inspection.ai_summary_source, 'ai')
        self.assertEqual(inspection.ai_summary_json['title'], 'Groq summary')
        self.assertIn('Groq generated summary.', inspection.ai_summary_html)

    def test_ai_summary_generation_handles_fenced_json_response(self):
        inspection = self._create_inspection(self.partner_2)
        self._set_failure_values(inspection)
        inspection.action_prepare()
        inspection.action_start()
        inspection.action_submit_for_review()

        fenced_payload = {
            'choices': [
                {
                    'message': {
                        'content': '```json\n%s\n```' % json.dumps(
                            {
                                'title': 'Groq summary',
                                'summary': 'Groq generated summary.',
                                'priority': 'high',
                                'top_findings': 'Finding one',
                                'recommended_actions': 'Action one',
                            }
                        )
                    }
                }
            ]
        }
        captured_request = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(fenced_payload).encode('utf-8')

        def fake_urlopen(request, timeout=20):
            captured_request['url'] = request.get_full_url()
            captured_request['authorization'] = request.get_header('Authorization')
            captured_request['model'] = json.loads(request.data.decode('utf-8'))['model']
            return FakeResponse()

        with patch.dict(os.environ, {'GROQ_API_KEY': 'test-groq-key', 'GROQ_MODEL': 'llama-3.1-70b-versatile'}, clear=False):
            with patch.object(urllib_request, 'urlopen', side_effect=fake_urlopen):
                inspection.action_generate_ai_summary()

        self.assertEqual(captured_request['url'], 'https://api.groq.com/openai/v1/chat/completions')
        self.assertEqual(captured_request['authorization'], 'Bearer test-groq-key')
        self.assertEqual(captured_request['model'], 'llama-3.1-70b-versatile')
        self.assertEqual(inspection.ai_summary_source, 'ai')
        self.assertEqual(inspection.ai_summary_json['title'], 'Groq summary')
        self.assertEqual(inspection.ai_summary_json['top_findings'], ['Finding one'])
        self.assertEqual(inspection.ai_summary_json['recommended_actions'], ['Action one'])
        self.assertIn('Groq generated summary.', inspection.ai_summary_html)

    def test_findings_and_certificates_link_to_inspection(self):
        inspection = self._create_inspection(self.partner)
        today = fields.Date.context_today(self.env.user)
        violation_tag = self.env['dm.food.violation.tag'].create(
            {
                'name': 'Cold Chain',
                'code': 'COLD_CHAIN',
                'company_id': inspection.company_id.id,
            }
        )

        finding = self.env['dm.food.finding'].create(
            {
                'inspection_id': inspection.id,
                'severity': 'critical',
                'status': 'open',
                'deadline_date': today + timedelta(days=1),
                'description': 'Cold room exceeded the allowed range.',
                'corrective_action': 'Service the compressor and recheck temperatures.',
                'tag_ids': [(6, 0, [violation_tag.id])],
            }
        )

        certificate = self.env['dm.food.certificate'].create(
            {
                'inspection_id': inspection.id,
                'issue_date': today,
                'expiry_date': today + timedelta(days=30),
                'status': 'active',
                'notes': 'Issued after corrective actions were confirmed.',
            }
        )

        inspection = self.Inspection.browse(inspection.id)

        self.assertNotEqual(finding.name, '/')
        self.assertNotEqual(certificate.name, '/')
        self.assertEqual(finding.establishment_id, inspection.establishment_id)
        self.assertEqual(certificate.establishment_id, inspection.establishment_id)
        self.assertEqual(inspection.finding_count, 1)
        self.assertEqual(inspection.certificate_count, 1)
        self.assertEqual(inspection.critical_finding_count, 1)

        finding_action = inspection.action_view_findings()
        certificate_action = inspection.action_view_certificates()

        self.assertEqual(finding_action['domain'], [('inspection_id', '=', inspection.id)])
        self.assertEqual(certificate_action['domain'], [('inspection_id', '=', inspection.id)])