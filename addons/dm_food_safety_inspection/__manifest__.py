# -*- coding: utf-8 -*-

{
    'name': 'Dubai Food Safety Inspection',
    'version': '19.0.1.0.0',
    'sequence': 150,
    'category': 'Services/Food Safety',
    'summary': 'Food safety inspections with checklist scoring and supervisor approval',
    'description': """
Food safety inspection workflow with weighted checklist scoring,
supervisor-gated outcomes, and demo-ready operational views.
    """,
    'author': 'Odoo S.A.',
    'website': 'https://www.odoo.com',
    'license': 'LGPL-3',
    'depends': ['mail'],
    'data': [
        'security/dm_food_safety_security.xml',
        'security/ir.model.access.csv',
        'data/dm_food_safety_sequence.xml',
        'data/dm_food_safety_stage_data.xml',
        'data/dm_food_safety_grade_data.xml',
        'data/dm_food_checklist_template_data.xml',
        'views/dm_food_inspection_views.xml',
        'views/dm_food_template_views.xml',
        'views/dm_food_stage_grade_views.xml',
    ],
    'demo': [
        'demo/dm_food_safety_demo.xml',
    ],
    'application': True,
    'installable': True,
}
