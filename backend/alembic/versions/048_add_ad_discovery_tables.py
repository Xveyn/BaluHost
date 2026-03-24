"""Add ad_discovery tables

Revision ID: 048_add_ad_discovery_tables
Revises: 047_wol_mac_server_profiles
Create Date: 2026-03-24

Adds tables for the Ad Discovery feature:
- ad_discovery_patterns: Heuristic patterns for domain scoring
- ad_discovery_reference_lists: Community blocklist sources
- ad_discovery_suspects: Domains flagged for potential blocking
- ad_discovery_custom_lists: User-created domain lists
- ad_discovery_custom_list_domains: Domains within custom lists
- ad_discovery_config: Singleton configuration row
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '048_add_ad_discovery_tables'
down_revision: Union[str, None] = '047_wol_mac_server_profiles'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- 1. ad_discovery_patterns ---
    op.create_table(
        'ad_discovery_patterns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pattern', sa.String(255), nullable=False),
        sa.Column('is_regex', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('weight', sa.Float(), nullable=False, server_default='0.5'),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ad_discovery_patterns_id', 'ad_discovery_patterns', ['id'])

    # --- 2. ad_discovery_reference_lists ---
    op.create_table(
        'ad_discovery_reference_lists',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('domain_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_fetched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('fetch_interval_hours', sa.Integer(), nullable=False, server_default='24'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('last_error_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ad_discovery_reference_lists_id', 'ad_discovery_reference_lists', ['id'])

    # --- 3. ad_discovery_suspects ---
    op.create_table(
        'ad_discovery_suspects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('domain', sa.String(253), nullable=False),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('query_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('heuristic_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('matched_patterns', sa.JSON(), nullable=True),
        sa.Column('community_hits', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('community_lists', sa.JSON(), nullable=True),
        sa.Column('source', sa.String(50), nullable=True),
        sa.Column('status', sa.String(30), nullable=False, server_default='suspect'),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('previous_score', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('domain', name='uq_ad_discovery_suspects_domain'),
    )
    op.create_index('ix_ad_discovery_suspects_id', 'ad_discovery_suspects', ['id'])
    op.create_index('ix_ad_discovery_suspects_domain', 'ad_discovery_suspects', ['domain'], unique=True)
    op.create_index('ix_ad_discovery_suspects_status', 'ad_discovery_suspects', ['status'])
    op.create_index(
        'ix_ad_discovery_suspects_status_score',
        'ad_discovery_suspects',
        ['status', 'heuristic_score'],
    )

    # --- 4. ad_discovery_custom_lists ---
    op.create_table(
        'ad_discovery_custom_lists',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('domain_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('deployed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('adlist_url', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_ad_discovery_custom_lists_name'),
    )
    op.create_index('ix_ad_discovery_custom_lists_id', 'ad_discovery_custom_lists', ['id'])

    # --- 5. ad_discovery_custom_list_domains ---
    op.create_table(
        'ad_discovery_custom_list_domains',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('list_id', sa.Integer(), nullable=False),
        sa.Column('domain', sa.String(253), nullable=False),
        sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['list_id'], ['ad_discovery_custom_lists.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('list_id', 'domain', name='uq_ad_discovery_custom_list_domains_list_domain'),
    )
    op.create_index('ix_ad_discovery_custom_list_domains_id', 'ad_discovery_custom_list_domains', ['id'])

    # --- 6. ad_discovery_config ---
    op.create_table(
        'ad_discovery_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('background_interval_hours', sa.Integer(), nullable=False, server_default='6'),
        sa.Column('heuristic_weight', sa.Float(), nullable=False, server_default='0.4'),
        sa.Column('community_weight', sa.Float(), nullable=False, server_default='0.6'),
        sa.Column('min_score', sa.Float(), nullable=False, server_default='0.15'),
        sa.Column('re_evaluation_threshold', sa.Float(), nullable=False, server_default='0.3'),
        sa.Column('background_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_analysis_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_analysis_watermark', sa.Float(), nullable=False, server_default='0.0'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ---------------------------------------------------------------
    # Seed default data
    # ---------------------------------------------------------------

    # -- Default patterns --
    patterns_table = sa.table(
        'ad_discovery_patterns',
        sa.column('pattern', sa.String),
        sa.column('is_regex', sa.Boolean),
        sa.column('weight', sa.Float),
        sa.column('category', sa.String),
        sa.column('is_default', sa.Boolean),
        sa.column('enabled', sa.Boolean),
    )

    default_patterns = [
        # ads
        ('ad.', False, 0.8, 'ads'),
        ('ads.', False, 0.8, 'ads'),
        ('adservice', False, 0.9, 'ads'),
        ('adserver', False, 0.8, 'ads'),
        ('doubleclick', False, 0.9, 'ads'),
        ('googlesyndication', False, 0.9, 'ads'),
        ('googleadservices', False, 0.9, 'ads'),
        ('moatads', False, 0.8, 'ads'),
        ('adnxs', False, 0.8, 'ads'),
        ('adsrvr', False, 0.8, 'ads'),
        # tracking
        ('tracker.', False, 0.7, 'tracking'),
        ('tracking.', False, 0.7, 'tracking'),
        ('pixel.', False, 0.6, 'tracking'),
        ('beacon.', False, 0.6, 'tracking'),
        ('collect.', False, 0.5, 'tracking'),
        ('telemetry.', False, 0.6, 'tracking'),
        ('clickstream', False, 0.7, 'tracking'),
        # analytics
        ('analytics.', False, 0.4, 'analytics'),
        ('metrics.', False, 0.3, 'analytics'),
        ('stats.', False, 0.3, 'analytics'),
        ('measure.', False, 0.3, 'analytics'),
        ('segment.io', False, 0.5, 'analytics'),
        ('hotjar', False, 0.5, 'analytics'),
        ('mouseflow', False, 0.5, 'analytics'),
        # fingerprinting
        ('fingerprint', False, 0.7, 'fingerprinting'),
        ('browser-update', False, 0.6, 'fingerprinting'),
        ('device-api', False, 0.6, 'fingerprinting'),
    ]

    op.bulk_insert(
        patterns_table,
        [
            {
                'pattern': p,
                'is_regex': is_regex,
                'weight': weight,
                'category': category,
                'is_default': True,
                'enabled': True,
            }
            for p, is_regex, weight, category in default_patterns
        ],
    )

    # -- Default reference lists --
    ref_lists_table = sa.table(
        'ad_discovery_reference_lists',
        sa.column('name', sa.String),
        sa.column('url', sa.String),
        sa.column('is_default', sa.Boolean),
        sa.column('enabled', sa.Boolean),
    )

    op.bulk_insert(
        ref_lists_table,
        [
            {
                'name': 'OISD Full',
                'url': 'https://big.oisd.nl/',
                'is_default': True,
                'enabled': False,
            },
            {
                'name': 'Hagezi Multi Pro',
                'url': 'https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/domains/pro.txt',
                'is_default': True,
                'enabled': False,
            },
            {
                'name': 'Steven Black Unified',
                'url': 'https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts',
                'is_default': True,
                'enabled': False,
            },
            {
                'name': 'EasyList Domains',
                'url': 'https://v.firebog.net/hosts/Easylist.txt',
                'is_default': True,
                'enabled': False,
            },
            {
                'name': 'AdGuard DNS Filter',
                'url': 'https://adguardteam.github.io/AdGuardSDNSFilter/Filters/filter.txt',
                'is_default': True,
                'enabled': False,
            },
        ],
    )

    # -- Config singleton --
    config_table = sa.table(
        'ad_discovery_config',
        sa.column('id', sa.Integer),
        sa.column('background_interval_hours', sa.Integer),
        sa.column('heuristic_weight', sa.Float),
        sa.column('community_weight', sa.Float),
        sa.column('min_score', sa.Float),
        sa.column('re_evaluation_threshold', sa.Float),
        sa.column('background_enabled', sa.Boolean),
        sa.column('last_analysis_watermark', sa.Float),
    )

    op.bulk_insert(
        config_table,
        [
            {
                'id': 1,
                'background_interval_hours': 6,
                'heuristic_weight': 0.4,
                'community_weight': 0.6,
                'min_score': 0.15,
                're_evaluation_threshold': 0.3,
                'background_enabled': True,
                'last_analysis_watermark': 0.0,
            }
        ],
    )


def downgrade() -> None:
    op.drop_table('ad_discovery_custom_list_domains')
    op.drop_table('ad_discovery_custom_lists')
    op.drop_table('ad_discovery_suspects')
    op.drop_table('ad_discovery_reference_lists')
    op.drop_table('ad_discovery_patterns')
    op.drop_table('ad_discovery_config')
