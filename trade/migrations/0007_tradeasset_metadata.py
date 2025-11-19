# Generated manually for adding metadata field to TradeAsset

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trade', '0006_trade_done_alter_tradestatus_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='tradeasset',
            name='metadata',
            field=models.JSONField(blank=True, help_text='Additional metadata for the asset (e.g., x_value for top_x protection)', null=True),
        ),
    ]

