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
    'depends': ['mail', 'web'],
    'data': [
        'security/dm_food_safety_security.xml',
        'security/ir.model.access.csv',
        'data/dm_food_safety_sequence.xml',
        'data/dm_food_safety_stage_data.xml',
        'data/dm_food_safety_grade_data.xml',
        'data/dm_food_checklist_template_data.xml',
        'views/dm_food_inspection_views.xml',
        'views/dm_food_inspection_integration_views.xml',
        'views/dm_food_template_views.xml',
        'views/dm_food_stage_grade_views.xml',
        'views/res_partner_food_profile_views.xml',
        'views/dm_food_finding_views.xml',
        'views/dm_food_certificate_views.xml',
        'views/dm_food_violation_tag_views.xml',
        'demo/dm_food_safety_demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dm_food_safety_inspection/static/src/dashboard/dm_food_safety_dashboard.js',
            'dm_food_safety_inspection/static/src/dashboard/dm_food_safety_dashboard.xml',
            'dm_food_safety_inspection/static/src/dashboard/dm_food_safety_dashboard.scss',
        ],
    },
    'application': True,
    'installable': True,
}
