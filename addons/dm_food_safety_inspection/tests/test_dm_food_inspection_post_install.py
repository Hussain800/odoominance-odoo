# -*- coding: utf-8 -*-

from odoo.tests import Form
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFoodSafetyInspectionPostInstall(TransactionCase):

    def test_form_creation_populates_template_lines(self):
        template = self.env.ref('dm_food_safety_inspection.dm_food_safety_template_restaurant')
        partner = self.env['res.partner'].create({
            'name': 'Palm Harbor Grill',
            'is_company': True,
            'city': 'Dubai',
            'country_id': self.env.ref('base.ae').id,
        })

        form = Form(self.env['dm.food.inspection'].with_user(self.env.ref('base.user_admin')))
        form.template_id = template
        form.establishment_id = partner
        inspection = form.save()

        self.assertEqual(inspection.stage_id.code, 'draft')
        self.assertEqual(inspection.line_count, len(template.line_ids))
        self.assertTrue(inspection.name)
