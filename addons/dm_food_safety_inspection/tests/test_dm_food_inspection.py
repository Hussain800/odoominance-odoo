# -*- coding: utf-8 -*-

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